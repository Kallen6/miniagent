import os
from openai import OpenAI
from dotenv import load_dotenv

from typing import Literal,TypedDict

from command_exec import exec_cmd
from build_tools import tool,get_registry,get_tools

load_dotenv()

SYS_PROMPT="你是一个ai助手"

class Message(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str

def system_msg(content: str = SYS_PROMPT) -> Message:
    return {"role": "system", "content": content}

def user_msg(content: str) -> Message:
    return {"role": "user", "content": content}

def assistant_msg(content: str) -> Message:
    return {"role": "assistant", "content": content}


def create_llm():
    return OpenAI(api_key=os.getenv("API_KEY"),
                  base_url=os.getenv("DS_URL"))

def get_llm_res(client:OpenAI,messages:list[dict[str,str]])->str:
    response = client.chat.completions.create(
                model="deepseek-flash",
                messages=messages,
                stream=False,
                reasoning_effort="high",
                extra_body={"thinking": {"type": "enabled"}},
                )
    return response.choices[0].message.content
@tool(description="nothing here")
def agent_loop():
    while True:
        ...



if __name__=="__main__":
    ...
    # content=input("[在本行输入问题]:")
    # messages=[system_msg(),
    #           user_msg(content=content)]
    # client=create_llm()
    # res=get_llm_res(client,messages)
    # print(res)
    print(get_registry())