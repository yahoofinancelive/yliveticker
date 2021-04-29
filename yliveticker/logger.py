import sys
from datetime import datetime

dest = sys.stderr
def writeline(msg):
    
    out_msg = f'[{datetime.now()}] {msg}\n'
    dest.write(out_msg)