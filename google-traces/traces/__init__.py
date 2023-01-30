import os

from dotenv import load_dotenv

from traces.logger import logger
from traces.filesystem import ROOT_DIR
from traces.mongo import MongoWrapper

load_dotenv(dotenv_path=os.path.join(ROOT_DIR, '.env'))

mongo_wrapper = MongoWrapper(
        host=os.getenv('MONGO_HOST'),
        port=os.getenv('MONGO_PORT'),
        user=os.getenv('MONGO_USER'),
        db=os.getenv('MONGO_DB'),
        password=os.getenv('MONGO_PASSWORD')
    )
mongo_wrapper.init()
logger.info('MongoDB connection established with success')
