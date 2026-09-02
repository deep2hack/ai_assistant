from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite+aiosqlite:///./messages.db"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


class MessageRecord(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String(50), nullable=False)  # whatsapp, email, telegram, instagram
    sender = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    is_summarized = Column(Boolean, default=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def save_message(platform: str, sender: str, content: str):
    async with AsyncSessionLocal() as session:
        msg = MessageRecord(platform=platform, sender=sender, content=content)
        session.add(msg)
        await session.commit()


async def fetch_unsummarized_messages():
    async with AsyncSessionLocal() as session:
        stmt = select(MessageRecord).where(MessageRecord.is_summarized == False)
        result = await session.execute(stmt)
        return result.scalars().all()


async def mark_messages_as_summarized(message_ids: list[int]):
    if not message_ids:
        return
    async with AsyncSessionLocal() as session:
        stmt = select(MessageRecord).where(MessageRecord.id.in_(message_ids))
        result = await session.execute(stmt)
        records = result.scalars().all()
        for record in records:
            record.is_summarized = True
        await session.commit()