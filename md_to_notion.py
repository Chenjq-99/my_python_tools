import re
import requests
import json
import os
import argparse
from tqdm import tqdm

def get_env_var(var_name):
    var = os.getenv(var_name)
    if var is None:
        raise ValueError(f"未找到环境变量{var_name}，请设置后重试")
    return var

NOTION_API_KEY = get_env_var("NOTION_API_KEY")
IMGBB_API_KEY = get_env_var("IMGBB_API_KEY")

parser = argparse.ArgumentParser(description="")
parser.add_argument('--id', type=str, required=True, help='Notion Page ID')
parser.add_argument('--path', type=str, required=True, help='本地文件路径')

args = parser.parse_args()
PAGE_ID = args.id
md_file_path = args.path

HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# =============== Notion Block生成函数 ===============
def create_block(block_data):
    url = f"https://api.notion.com/v1/blocks/{PAGE_ID}/children"
    response = requests.patch(url, headers=HEADERS, data=json.dumps({"children": [block_data]}))
    if not response.ok:
        print(f"Failed to add block: {response.text}")
    return response.ok

def create_text_block(text, block_type="paragraph"):
    return {
        "object": "block",
        "type": block_type,
        block_type: {
            "rich_text": [{"type": "text", "text": {"content": text}}]
        }
    }

def create_rich_text_block(rich_text_parts):
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": rich_text_parts
        }
    }

def create_image_block(url):
    return {
        "object": "block",
        "type": "image",
        "image": {
            "type": "external",
            "external": {"url": url}
        }
    }

def create_equation_block(equation):
    return {
        "object": "block",
        "type": "equation",
        "equation": {"expression": equation}
    }

# =============== 上传本地图片到imgbb ===============
def upload_image_to_imgbb(image_path):
    with open(image_path, "rb") as file:
        response = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": IMGBB_API_KEY},
            files={"image": file}
        )
    if response.ok:
        return response.json()["data"]["url"]
    else:
        print(f"图片上传失败: {response.text}")
        return None

# =============== 行内公式拆分函数 ===============
def process_text_block(line):
    """
    分割一行文本，解析行内公式 ($...$) 和加粗文本 (**...**)
    返回符合Notion rich_text格式的列表
    """
    parts = []
    pattern = re.compile(r'(\$\$.*?\$\$|\$.*?\$|\*\*.*?\*\*)')
    last_end = 0

    for match in pattern.finditer(line):
        # 处理普通文本部分
        if match.start() > last_end:
            parts.append({
                "type": "text",
                "text": {"content": line[last_end:match.start()]}
            })

        content = match.group()
        if content.startswith("$$") and content.endswith("$$"):
            # 如果是块级公式，跳过（不在行内解析处理）
            parts.append({
                "type": "text",
                "text": {"content": content}
            })
        elif content.startswith("$") and content.endswith("$"):
            # 行内数学公式
            parts.append({
                "type": "equation",
                "equation": {"expression": content[1:-1]}  # 去掉两边$
            })
                
        elif content.startswith("**") and content.endswith("**"):
            # 加粗文本
            parts.append({
                "type": "text",
                "text": {"content": content[2:-2]},  # 去掉两边**
                "annotations": {"bold": True}
            })

        last_end = match.end()

    # 处理末尾剩余文本
    if last_end < len(line):
        parts.append({
            "type": "text",
            "text": {"content": line[last_end:]}
        })

    return parts

# =============== 主逻辑：解析Markdown并上传 ===============
def parse_markdown_and_upload(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    current_equation = None  # 标识块级数学公式

    for line in tqdm(lines):
        line = line.strip()

        # 标题处理
        if line.startswith("# "):
            create_block(create_text_block(line[2:], "heading_1"))
        elif line.startswith("## "):
            create_block(create_text_block(line[3:], "heading_2"))
        elif line.startswith("### "):
            create_block(create_text_block(line[4:], "heading_3"))

        # 块级数学公式处理
        elif line == "$$":
            if current_equation is None:
                current_equation = []
            else:
                create_block(create_equation_block("\n".join(current_equation)))
                current_equation = None
            continue
        elif current_equation is not None:
            current_equation.append(line)
            continue

        # 图片处理（支持本地和外链图片）
        elif match := re.match(r"!\[(.*?)\]\((.*?)\)", line):
            alt_text, image_path = match.groups()

            if image_path.startswith("http"):
                image_url = image_path
            else:
                if not os.path.exists(image_path):
                    image_path = os.path.join(os.path.dirname(file_path), image_path)
                if not os.path.exists(image_path):
                    raise ValueError(f"图片文件不存在: {image_path}") 
                image_url = upload_image_to_imgbb(image_path)

            if image_url:
                    create_block(create_image_block(image_url))
                    if alt_text:
                        create_block(create_text_block(alt_text))

        # 普通段落+行内公式处理
        elif line:
            rich_text_parts = process_text_block(line)
            create_block(create_rich_text_block(rich_text_parts))

if __name__ == "__main__":
    parse_markdown_and_upload(md_file_path)