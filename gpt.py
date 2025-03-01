import openai
import sys
import os
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

# 设置 OpenAI API Key
def get_env_var(var_name):
    var = os.getenv(var_name)
    if var is None:
        raise ValueError(f"未找到环境变量{var_name}，请设置后重试")
    return var

OPENAI_API_KEY = get_env_var("OPENAI_API_KEY")

console = Console()

def chat_with_gpt(prompt):
    """调用 OpenAI GPT 生成响应"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",  # 选择 GPT-4 或 gpt-3.5-turbo
            messages=[{"role": "user", "content": prompt}],
            api_key=OPENAI_API_KEY
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"[red]Error:[/red] {e}"

def main():
    """主函数"""
    # 检测是否有管道输入
    if not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
    elif len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
    else:
        console.print("[bold yellow]Usage:[/bold yellow] ai <your question> OR echo 'question' | ai", style="italic")
        return

    # 显示用户输入
    console.print(Panel(prompt, title="[bold green]You[/bold green]", expand=False))

    # 获取 GPT 响应
    # 节省tokens
    prompt += '简要回答'
    response = chat_with_gpt(prompt)

    # 以 Markdown 格式美化 AI 响应
    console.print(Panel(Markdown(response), title="[bold cyan]ChatGPT[/bold cyan]", expand=False))

if __name__ == "__main__":
    main()
