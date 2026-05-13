import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from leRH.db.base import async_session_factory
from leRH.core.credits import CreditManager
from leRH.db.models import User
from leRH.db.repository import UserRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_concurrency():
    user_id = "8b1dc71ec647" # From the user's logs
    
    async with async_session_factory() as session:
        # 1. Start a transaction and DO A WRITE (to hold the lock)
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        if not user:
            logger.error("User not found")
            return
        
        logger.info("Session 1: Modifying user (write lock acquired)")
        user.activity = "Testing Lock " + str(asyncio.get_event_loop().time())
        await session.flush()
        
        # 2. While Session 1 is open and has a write lock, try to deduct credits in Session 2
        logger.info("Session 2: Trying to deduct credits (should wait or retry)")
        credit_mgr = CreditManager()
        
        # We'll run the deduction in a task so it doesn't block this one if it waits
        deduct_task = asyncio.create_task(credit_mgr.deduct(user_id, 1, reason="test_lock"))
        
        logger.info("Session 1: Waiting 2 seconds before committing...")
        await asyncio.sleep(2)
        
        logger.info("Session 1: Committing...")
        await session.commit()
        
        # 3. Wait for the deduction task to finish
        result = await deduct_task
        logger.info("Session 2 result: %s", result)

if __name__ == "__main__":
    asyncio.run(test_concurrency())
