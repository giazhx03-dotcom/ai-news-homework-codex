"""集中维护的 RSS 标题、摘要和实体规则。示例见 docs/rules.md。"""
import re

CATEGORIES = ("模型与研究", "产品与工具", "行业与政策", "待确认")


def terms(english, chinese):
    # ASCII 边界允许中文与英文实体紧邻，同时避免 email、paid、again 等误判。
    return re.compile(r"(?<![a-z0-9_])(?:" + english + r")(?![a-z0-9_])|(?:" + chinese + ")", re.I)


AI = terms(
    r"ai|a\.i\.|artificial intelligence|machine learning|deep learning|neural networks?|"
    r"large language models?|language models?|foundation models?|generative models?|"
    r"llms?|coding agents?|agentic|chatbots?|openai|anthropic|deepmind|chatgpt|"
    r"gpt(?:[- ]?\d[.\w-]*)?|deepseek|hugging face|llama[ -]?\d+|"
    r"codex and astra|gemini[ -]?\d[.\w-]*|github copilot|chatgpt codex|trainium|tpu[s]?",
    "人工智[能慧]|大语言模型|大模型|生成式模型|机器学习|深度学习|神经网络|智能体|智谱|通义千问|算力芯片")
# Remove an editorial credit, preserving substantive references to AI tools and generated media.
EN_CREDIT = re.compile(
    r"\b(?:this |the )?(?:article|report|story|post|text|summary|translation|recap)?\s*"
    r"(?:(?:was|is|has been)\s+)?(?:written|translated|summari[sz]ed|edited|generated|produced|created)"
    r"\s+(?:by|using|with(?:(?: the)? (?:help|assistance|aid) (?:of|from))?)\s+(?:an?\s+)?"
    r"(?:ai|artificial intelligence|chatgpt)\b(?:[- ](?:writing )?tools?)?", re.I)
ZH_CREDIT = re.compile(
    r"(?:本文|本篇|本条|本报道|本稿|此文|该文|文章|摘要|报道|稿件)(?:内容)?\s*(?:系|为|系由)?"
    r"(?:由|使用|借助|采用|通过|经)?\s*(?:人工智能|AI|ChatGPT)\s*(?:写作)?(?:工具|技术)?\s*"
    r"(?:辅助|协助|自动)?(?:撰写|写作|编写|生成|翻译|润色)|"
    r"(?:由|借助)\s*(?:AI|人工智能)\s*(?:工具)?(?:辅助)?(?:撰写|生成)(?=[。！.!）)\s]|$)", re.I)
CREDIT_LABEL = re.compile(
    r"\bai[- ](?:generated|assisted|written|translated)\s+(?:article|recap|report|translation)\b"
    r"|(?:^|[.!?。！？])\s*ai[- ](?:generated|written|assisted)\s*[.!。]?$|[（(]\s*(?:AI[- ](?:generated|written)|AI\s*(?:辅助)?(?:撰写|写作|生成))\s*[）)]", re.I)
AMBIGUOUS = terms(r"claude|gemini|codex|copilot|nvidia", "英伟达")
TECH_CONTEXT = terms(r"models?|assistant|agents?|coding|prompt\w*|chat|cloud|gpus?|chips?|"
                     r"data cent(?:er|re)s?|software|launch\w*|developers?|ceo|board member|"
                     r"reinstated|comput(?:e|ing)|inference|semiconductor\w*", "编程|人工智能|推出|发布|模型|助手|芯片|算力|数据中心|董事|首席执行官")
INDUSTRY = terms(
    r"regulat\w*|financ(?:e|ing)|funding|fundrais\w*|raises?|raised|invest(?:s|ment|ors?)?|"
    r"acquir\w*|acquisition|lawsuits?|sues?|sued|attorneys? general|senators?|legislation|"
    r"regulators?|polic(?:y|ies)|chips?|gpus?|data cent(?:er|re)s?|partnership|"
    r"valuations?|ipo|export controls?|layoffs?|copyright|ceo|board member|"
    r"reinstated|bankruptcy|ban(?:s|ned|ning)?|regulatory|cyber agency",
    "融资|募资|并购|收购|估值|监管|立法|诉讼|版权|芯片|算力|数据中心|投资|合作协议|行业发展")
RESEARCH = terms(
    r"research(?:ers?)?|stud(?:y|ies)|benchmarks?|datasets?|papers?|training|pretrain\w*|"
    r"reasoning|architectures?|weights|models?|neural networks?|evaluat\w*|"
    r"discove(?:r|rs|red|ry)|scienti(?:st|fic)\w*",
    "模型|研究|基准|评测|论文|训练|数据集|开源权重|科学发现")
PRODUCT = terms(
    r"products?|tools?|apps?|platforms?|releases?|launch(?:es|ed)?|introduc(?:e|es|ing)|"
    r"assistants?|agents?|agentic|features?|apis?|coding|deploy\w*|rolls? out|"
    r"integrat\w*|workflows?|chatbots?|copilot|codex",
    "产品|工具|应用|助手|智能体|上线|推出|工作流|开发平台|部署")
POSSIBLE = terms(r"diffusion models?|transformer models?|inference accelerators?|tensor cores?", "推理加速器|扩散模型|推理模型")
BENCHMARK = terms(r"benchmarks?|peer-reviewed|controlled trials?", "基准测试|基准评测|发表论文")


def clean_credit(text):
    return CREDIT_LABEL.sub(" ", ZH_CREDIT.sub(" ", EN_CREDIT.sub(" ", text)))


def classify(entry):
    title = clean_credit(entry["title"])
    summary = clean_credit(entry.get("summary") or "")
    body = title + " " + summary
    if not (AI.search(body) or (AMBIGUOUS.search(body) and TECH_CONTEXT.search(body))):
        return CATEGORIES[3] if POSSIBLE.search(body) else None
    if BENCHMARK.search(body) and not INDUSTRY.search(title):
        return CATEGORIES[0]
    for passage in (title, summary, " ".join(entry.get("tags") or [])):
        for pattern, category in ((INDUSTRY, CATEGORIES[2]), (RESEARCH, CATEGORIES[0]), (PRODUCT, CATEGORIES[1])):
            if pattern.search(passage):
                return category
    return CATEGORIES[3]
