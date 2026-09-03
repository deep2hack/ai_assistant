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
    platform = Column(String(50), nullable=False)
    sender = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    is_summarized = Column(Boolean, default=False)


class PendingAction(Base):
    __tablename__ = "pending_actions"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String(50), nullable=False)
    recipient = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=True)
    draft_body = Column(Text, nullable=False)
    status = Column(String(50), default="pending")

    # Property taaki main.py proposed_text ya draft_body dono use kar sake
    @property
    def proposed_text(self):
        return self.draft_body

    @proposed_text.setter
    def proposed_text(self, value):
        self.draft_body = value


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


# Alias for main.py import compatibility
mark_messages_summarized = mark_messages_as_summarized


async def create_pending_action(
    platform: str, recipient: str, draft_body: str, subject: str = None
) -> int:
    async with AsyncSessionLocal() as session:
        action = PendingAction(
            platform=platform,
            recipient=recipient,
            draft_body=draft_body,
            subject=subject,
        )
        session.add(action)
        await session.commit()
        await session.refresh(action)
        return action.id


# Alias for main.py import compatibility
async def save_pending_action(platform: str, recipient: str, proposed_text: str):
    return await create_pending_action(
        platform=platform, recipient=recipient, draft_body=proposed_text
    )


async def get_pending_action(action_id: int):
    async with AsyncSessionLocal() as session:
        stmt = select(PendingAction).where(PendingAction.id == action_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def update_pending_action_text(action_id: int, new_text: str):
    async with AsyncSessionLocal() as session:
        action = await session.get(PendingAction, action_id)
        if action:
            action.draft_body = new_text
            action.status = "PENDING"
            await session.commit()
            await session.refresh(action)
            return action
        return None


async def set_action_status(action_id: int, status: str):
    async with AsyncSessionLocal() as session:
        action = await session.get(PendingAction, action_id)
        if action:
            action.status = status
            await session.commit()
            await session.refresh(action)
            return action
        return None


update_pending_action_status = set_action_status


async def get_editing_action():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PendingAction)
            .where(PendingAction.status == "EDITING")
            .order_by(PendingAction.id.desc())
        )
        return result.scalars().first()