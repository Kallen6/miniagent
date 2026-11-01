import subprocess
from subprocess import CompletedProcess

def show_cmd_res(result:CompletedProcess):
    print(f"[exit]:<{result.returncode}>\n[stdout]:<{result.stdout}>\n[stderr]:<{result.stderr}>")

def exec_cmd(cmd:str):
    res=subprocess.run(
        cmd, 
        shell=True,
        capture_output=True,
        text=True,
    )
    show_cmd_res(res)

if __name__=="__main__":
    ...
    exec_cmd("ipconfig")