import os
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig, TextStreamer

# ==========================================
# 1. 本地路径与基础配置
# ==========================================
model_path = r"D:\Gemma4_Local"

print(f"🔍 正在唤醒 RTX 5070...")

if "http_proxy" in os.environ: del os.environ["http_proxy"]
if "https_proxy" in os.environ: del os.environ["https_proxy"]

# ==========================================
# 2. 硬件检测与模型加载
# ==========================================
if torch.cuda.is_available():
    device = "cuda:0" 
    load_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True
    )
else:
    print("❌ 致命错误：未识别到 GPU！")
    exit()

try:
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        quantization_config=load_config,
        device_map={"": device}, 
        local_files_only=True
    )
    print("✅ 智能大脑已满血载入 5070 显存！")

    # ==========================================
    # 3. 流式推理函数
    # ==========================================
    def chat(prompt):
        messages = [{"role": "user", "content": prompt}]
        
        # 【修复】return_dict=True 返回完整 BatchEncoding，解决 KeyError: 'shape'
        inputs = tokenizer.apply_chat_template(
            messages, 
            add_generation_prompt=True, 
            return_tensors="pt",
            return_dict=True
        ).to(device)
        
        streamer = TextStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)
        
        with torch.no_grad():
            print("\n🌟 Gemma 4 正在思考...\n")
            model.generate(
                **inputs,
                max_new_tokens=512,
                do_sample=True,
                temperature=0.7,
                pad_token_id=tokenizer.eos_token_id,
                streamer=streamer
            )
            print("\n")

    if __name__ == "__main__":
        print("\n🚀 开始 A 股项目推理测试...")
        chat("你好！既然环境已经打通，下一步我们如何把 A 股历史数据喂给你进行分析？请简短回答。")

except Exception as e:
    import traceback
    print(f"❌ 运行失败，错误堆栈:\n{traceback.format_exc()}")