"""Optional official GPT login/extraction. Does not import any existing auth files."""
import argparse
import json
import sys
import webbrowser
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.providers.codex import CodexImageProvider
from backend.providers.qwen import ProviderError
from extractor_core.io import read_image, save_png


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['login','extract'])
    parser.add_argument('--input',type=Path);parser.add_argument('--output',type=Path)
    parser.add_argument('--allow-usage',action='store_true',help='Explicitly accept Codex quota usage; no API-key fallback')
    args=parser.parse_args()
    try:
        provider=CodexImageProvider(allow_usage=args.allow_usage)
        if args.action=='login':
            print('请在即将打开的官方页面完成登录；本程序不读取或显示登录凭据。',flush=True)
            result=provider.login(webbrowser.open)
        else:
            if not args.input or not args.output: parser.error('extract 需要 --input 与 --output')
            image=read_image(args.input.read_bytes())
            result_image=provider.edit(image)
            save_png(args.output,result_image)
            result={'status':'needs_review','output':str(args.output),'preserves_source_rgb':False}
        print(json.dumps(result,ensure_ascii=False));return 0
    except (ValueError,OSError):
        print('官方 Codex 桥接未完成；请核对 CLI、本人登录与真实透明图输出。不会重试或改用 API Key。',file=sys.stderr)
        return 1


if __name__=='__main__': raise SystemExit(main())
