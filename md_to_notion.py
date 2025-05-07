import re
import requests
import json
import os
import argparse
from tqdm import tqdm
from typing import Optional, Dict, List, Any

def get_env_var(var_name: str) -> str:
    """获取环境变量值
    
    Args:
        var_name: 环境变量名称
        
    Returns:
        环境变量的值
        
    Raises:
        ValueError: 当环境变量不存在或为空时抛出异常
    """
    var = os.getenv(var_name)
    if not var or not var.strip():
        raise ValueError(f"环境变量 {var_name} 未设置或为空，请设置有效的值后重试")
    return var.strip()

class NotionClient:
    def __init__(self, api_key: str, page_id: str):
        self.api_key = api_key
        self.page_id = page_id
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
    def create_block(self, block_data: Dict[str, Any]) -> bool:
        """创建Notion块"""
        url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
        response = requests.patch(url, headers=self.headers, 
                                data=json.dumps({"children": [block_data]}))
        if not response.ok:
            print(f"创建块失败: {response.text}")
            return False
        return True

class ImageUploader:
    def __init__(self, api_key: str):
        self.api_key = api_key
        
    def upload_to_imgbb(self, image_path: str) -> Optional[str]:
        """上传图片到imgbb"""
        try:
            with open(image_path, "rb") as file:
                response = requests.post(
                    "https://api.imgbb.com/1/upload",
                    data={"key": self.api_key},
                    files={"image": file}
                )
            if response.ok:
                return response.json()["data"]["url"]
            print(f"图片上传失败: {response.text}")
        except Exception as e:
            print(f"图片上传出错: {str(e)}")
        return None

class NotionBlockFactory:
    @staticmethod
    def create_text_block(text: str, block_type: str = "paragraph") -> Dict[str, Any]:
        """创建文本块"""
        return {
            "object": "block",
            "type": block_type,
            block_type: {
                "rich_text": [{"type": "text", "text": {"content": text}}]
            }
        }

    @staticmethod
    def create_rich_text_block(rich_text_parts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """创建富文本块"""
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": rich_text_parts
            }
        }

    @staticmethod
    def create_image_block(url: str) -> Dict[str, Any]:
        """创建图片块"""
        return {
            "object": "block",
            "type": "image",
            "image": {
                "type": "external",
                "external": {"url": url}
            }
        }

    @staticmethod
    def create_equation_block(equation: str) -> Dict[str, Any]:
        """创建数学公式块"""
        return {
            "object": "block",
            "type": "equation",
            "equation": {"expression": equation}
        }

class MarkdownParser:
    def __init__(self, notion_client: NotionClient, image_uploader: ImageUploader):
        self.notion_client = notion_client
        self.image_uploader = image_uploader
        self.block_factory = NotionBlockFactory()
        
    def process_text_block(self, line: str) -> List[Dict[str, Any]]:
        """处理文本块,解析行内公式和加粗文本"""
        parts = []
        pattern = re.compile(r'(\$\$.*?\$\$|\$.*?\$|\*\*.*?\*\*)')
        last_end = 0

        for match in pattern.finditer(line):
            if match.start() > last_end:
                parts.append({
                    "type": "text",
                    "text": {"content": line[last_end:match.start()]}
                })

            content = match.group()
            if content.startswith("$$") and content.endswith("$$"):
                parts.append({
                    "type": "text",
                    "text": {"content": content}
                })
            elif content.startswith("$") and content.endswith("$"):
                parts.append({
                    "type": "equation",
                    "equation": {"expression": content[1:-1]}
                })
            elif content.startswith("**") and content.endswith("**"):
                parts.append({
                    "type": "text",
                    "text": {"content": content[2:-2]},
                    "annotations": {"bold": True}
                })

            last_end = match.end()

        if last_end < len(line):
            parts.append({
                "type": "text",
                "text": {"content": line[last_end:]}
            })

        return parts

    def parse_and_upload(self, file_path: str) -> None:
        """解析Markdown文件并上传到Notion"""
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        current_equation = None

        for line in tqdm(lines, desc="处理Markdown"):
            line = line.strip()
            if not line:
                continue

            # 标题处理
            if line.startswith(("# ", "## ", "### ")):
                level = len(line.split()[0])  # 获取#的数量
                self.notion_client.create_block(
                    self.block_factory.create_text_block(
                        line[level+1:], f"heading_{level}"
                    )
                )
                continue

            # 块级数学公式处理
            if line == "$$":
                if current_equation is None:
                    current_equation = []
                else:
                    self.notion_client.create_block(
                        self.block_factory.create_equation_block("\n".join(current_equation))
                    )
                    current_equation = None
                continue
            
            if current_equation is not None:
                current_equation.append(line)
                continue

            # 图片处理
            if match := re.match(r"!\[(.*?)\]\((.*?)\)", line):
                alt_text, image_path = match.groups()
                image_url = (image_path if image_path.startswith("http") else
                           self._resolve_local_image(image_path, file_path))
                
                if image_url:
                    self.notion_client.create_block(
                        self.block_factory.create_image_block(image_url)
                    )
                    if alt_text:
                        self.notion_client.create_block(
                            self.block_factory.create_text_block(alt_text)
                        )
                continue

            # 普通段落处理
            rich_text_parts = self.process_text_block(line)
            self.notion_client.create_block(
                self.block_factory.create_rich_text_block(rich_text_parts)
            )

    def _resolve_local_image(self, image_path: str, md_file_path: str) -> Optional[str]:
        """解析本地图片路径并上传"""
        if not os.path.exists(image_path):
            image_path = os.path.join(os.path.dirname(md_file_path), image_path)
        if not os.path.exists(image_path):
            print(f"警告: 图片文件不存在: {image_path}")
            return None
        return self.image_uploader.upload_to_imgbb(image_path)

def main():
    parser = argparse.ArgumentParser(description="将Markdown文件转换并上传到Notion")
    parser.add_argument('-i', '--id', type=str, required=True, help='Notion Page ID')
    parser.add_argument('-p', '--path', type=str, required=True, help='本地Markdown文件路径')
    args = parser.parse_args()

    # 初始化所需的API密钥
    notion_api_key = get_env_var("NOTION_API_KEY")
    imgbb_api_key = get_env_var("IMGBB_API_KEY")
    
    # 格式化Notion页面ID
    page_id = f"{args.id[:8]}-{args.id[8:12]}-{args.id[12:16]}-{args.id[16:20]}-{args.id[20:]}"
    
    # 初始化客户端
    notion_client = NotionClient(notion_api_key, page_id)
    image_uploader = ImageUploader(imgbb_api_key)
    
    # 解析并上传
    parser = MarkdownParser(notion_client, image_uploader)
    parser.parse_and_upload(args.path)

if __name__ == "__main__":
    main()