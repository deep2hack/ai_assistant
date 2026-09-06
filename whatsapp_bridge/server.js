const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const express = require('express');
const axios = require('axios');

const app = express();
app.use(express.json());

const FASTAPI_WEBHOOK_URL = 'http://127.0.0.1:8000/webhook/whatsapp';

let lastActiveJid = null;

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

// Capture only real incoming messages and permanently stop self-reply looping
client.on('message_create', async (msg) => {
    try {
        // 1. DROP ALL MESSAGES SENT BY THE BOT ITSELF
        if (msg.fromMe) {
            return;
        }

        // 2. Ignore group chats
        if ((msg.from && msg.from.includes('@g.us')) || (msg.to && msg.to.includes('@g.us'))) {
            return;
        }

        const body = (msg.body || '').trim();
        if (!body) return;

        const effectiveSender = msg.from;
        lastActiveJid = effectiveSender;

        let displayName = null;

        try {
            const contact = await msg.getContact();
            if (contact) {
                if (contact.name && contact.name.trim()) {
                    displayName = contact.name.trim();
                } else if (contact.pushname && contact.pushname.trim()) {
                    displayName = contact.pushname.trim();
                } else if (contact.number && contact.number.trim()) {
                    displayName = `+${contact.number.trim()}`;
                }
            }
        } catch (e) {
            console.log('Contact name lookup skipped:', e.message);
        }

        if (!displayName) {
            displayName = effectiveSender;
        }

        await axios.post(FASTAPI_WEBHOOK_URL, {
            entry: [{
                changes: [{
                    value: {
                        messages: [{
                            from: displayName,
                            raw_id: effectiveSender,
                            type: 'text',
                            text: { body: body }
                        }]
                    }
                }]
            }]
        });

        console.log(`Forwarded WhatsApp message from: ${displayName} (${effectiveSender}) to FastAPI`);
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

        // 1. Resolve 'Self' or names without numbers
        const digitsOnly = chatId.replace(/\D/g, '');
        if (chatId.toLowerCase() === 'self' || (!chatId.includes('@') && digitsOnly.length === 0)) {
            if (lastActiveJid) {
                console.log(`Resolved target "${chatId}" to lastActiveJid: ${lastActiveJid}`);
                chatId = lastActiveJid;
            } else if (client.info && client.info.wid) {
                chatId = client.info.wid._serialized;
                console.log(`Resolved target "${chatId}" to client JID: ${chatId}`);
            } else {
                return res.status(400).json({
                    error: `Target "${chatId}" cannot be resolved. No active sender JID available.`
                });
            }
        } 
        // 2. Format pure phone digits to standard WhatsApp format
        else if (!chatId.includes('@lid') && !chatId.includes('@c.us')) {
            if (digitsOnly.length === 10) {
                chatId = `91${digitsOnly}@c.us`;
            } else {
                chatId = `${digitsOnly}@c.us`;
            }
        }

        console.log(`Dispatching message to target ChatId: ${chatId}`);

        // Try direct sendMessage first; fallback to getChatById for LID routing
        try {
            await client.sendMessage(chatId, message);
        } catch (sendErr) {
            console.log(`Direct send failed (${sendErr.message}), attempting fallback via getChatById...`);
            const chat = await client.getChatById(chatId);
            if (chat && typeof chat.sendMessage === 'function') {
                await chat.sendMessage(message);
            } else {
                throw sendErr;
            }
        }

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