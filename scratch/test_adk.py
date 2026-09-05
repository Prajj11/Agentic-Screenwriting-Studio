import asyncio
import os
import sys
from pathlib import Path
import dotenv

dotenv.load_dotenv('backend/.env')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = os.path.abspath('test_creds.json')
os.environ['GOOGLE_CLOUD_PROJECT'] = 'gen-lang-client-0423661956'
os.environ['GOOGLE_CLOUD_LOCATION'] = 'us-central1'
os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = 'true'

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'backend'))

import vertexai
vertexai.init(project='gen-lang-client-0423661956', location='us-central1')

from agents.showrunner import create_showrunner
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

async def main():
    agent = create_showrunner()
    session_service = InMemorySessionService()
    runner = Runner(agent=agent, app_name='test_app', session_service=session_service)
    await session_service.create_session(app_name='test_app', user_id='u1', session_id='s1')
    
    msg = types.Content(role='user', parts=[types.Part(text='Hello Showrunner!')])
    async for event in runner.run_async(
        user_id='u1',
        session_id='s1',
        new_message=msg,
    ):
        print('Event:', event)

if __name__ == '__main__':
    asyncio.run(main())
