from ib_insync import *
from dotenv import load_dotenv
import os

load_dotenv()

ib = IB()

try:
    ib.connect(
        host=os.getenv('IB_HOST', '127.0.0.1'),
        port=int(os.getenv('IB_PORT', 4002)),
        clientId=int(os.getenv('IB_CLIENT_ID', 1))
    )
    print('',flush=True)
    print('=' * 40)
    print('  SUCCESS: Connected to IBKR!')
    print('=' * 40)
    print(f'  Account: {ib.managedAccounts()}')
    print(f'  Connected: {ib.isConnected()}')
    print('=' * 40)
    ib.disconnect()
except Exception as e:
    print(f'FAILED: {e}')
    print('Check that IB Gateway is running: docker compose ps')
