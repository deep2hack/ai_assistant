const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const express = require('express');
const axios = require('axios');

const app = express();
app.use(express.json());

const FASTAPI_WEBHOOK_URL = 'http://127.0.0.1:8000/webhook/whatsapp';

const client = new Client({
    authStrategy: new LocalAuth({ dataPath: './business_session' }),
    puppeteer: {
        headless: true,
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--no-first-run',
            '--no-zygote',
            '--disable-gpu'
        ]
    }
});

client.on('qr', (qr) => {
    console.log('\n--- SCAN THIS QR CODE USING WHATSAPP BUSINESS APP ---');
    qrcode.generate(qr, { small: true });
});

client.on('ready', () => {
    console.log('✅ WhatsApp Business Client authenticated and ready!');
});

// Incoming message handler with Name and Phone Number resolution
client.on('message', async (msg) => {
    try {
        if (msg.from.includes('@g.us')) return;

        let displayName = null;

        try {
            const contact = await msg.getContact();
            if (contact) {
                // Priority: Saved Name -> Public Pushname -> Real Phone Number
                if (contact.name && contact.name.trim() !== '') {
                    displayName = contact.name.trim();
                } else if (contact.pushname && contact.pushname.trim() !== '') {
                    displayName = contact.pushname.trim();
                } else if (contact.number && contact.number.trim() !== '') {
                    displayName = `+${contact.number.trim()}`;
                }
            }
        } catch (contactErr) {
            console.log('Contact resolution fallback triggered');
        }

        // Fallback: If contact resolution fails completely
        if (!displayName) {
            displayName = msg.from;
        }

        const body = msg.body;

        await axios.post(FASTAPI_WEBHOOK_URL, {
            entry: [{
                changes: [{
                    value: {
                        messages: [{
                            from: displayName,     // Clean Name or Phone number (for UI/Telegram display)
                            raw_id: msg.from,      // Exact destination JID (@lid or @c.us for sending replies)
                            type: 'text',
                            text: { body: body }
                        }]
                    }
                }]
            }]
        });

        console.log(`Forwarded WhatsApp message from: ${displayName} (${msg.from}) to FastAPI`);
    } catch (err) {
        console.error('Error forwarding message to FastAPI:', err.message);
    }
});

// Outbound message dispatcher
app.post('/send-message', async (req, res) => {
    const { recipient, message } = req.body;

    if (!recipient || !message) {
        return res.status(400).json({ error: 'recipient and message are required' });
    }

    try {
        let chatId = recipient.toString().trim();

        // 1. Agar ID me pehle se valid JID format (@lid ya @c.us) hai
        if (chatId.includes('@lid') || chatId.includes('@c.us')) {
            // Keep original JID as is
        } 
        // 2. Agar raw digits ya phone number pass hua ho
        else {
            const cleanDigits = chatId.replace(/\D/g, '');
            if (cleanDigits.length >= 13 && cleanDigits.startsWith('138')) {
                chatId = `${cleanDigits}@lid`;
            } else if (cleanDigits.length === 10) {
                chatId = `91${cleanDigits}@c.us`;
            } else {
                chatId = `${cleanDigits}@c.us`;
            }
        }

        console.log(`Sending message to target ChatId: ${chatId}`);
        await client.sendMessage(chatId, message);
        console.log(`Dispatched WhatsApp message successfully to ${chatId}`);

        return res.json({ status: 'success' });
    } catch (err) {
        console.error('Error sending WhatsApp message:', err.message);
        return res.status(500).json({ error: err.message });
    }
});

client.initialize();

const PORT = 3001;
app.listen(PORT, () => {
    console.log(`WhatsApp Bridge running on http://127.0.0.1:${PORT}`);
});