import sys
sys.path.insert(0, ".")
import inspect
from google.adk.agents import LlmAgent
print(inspect.signature(LlmAgent.__init__))
