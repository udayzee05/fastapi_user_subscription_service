import motor.motor_asyncio

from api.config import settings

# connect to mongodb
client = motor.motor_asyncio.AsyncIOMotorClient(settings.MONGODB_URL)

# create the news_summary_users database
db = client[settings.DB_NAME]