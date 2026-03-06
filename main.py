from dotenv import load_dotenv
from vercel.sandbox import Sandbox
 
load_dotenv('.env.local')
 
sandbox = Sandbox.create()

result = sandbox.run_command('echo', ['Hello from Vercel Sandbox!'])
print(result.stdout())