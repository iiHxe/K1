# Run: python -m streamlit run app.py
import os, re, json, time, requests
from dataclasses import dataclass
from typing import List, Optional, Dict
from dotenv import load_dotenv
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import date

# =============== ENV / FLAGS ===============
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
FDC_API_KEY    = os.getenv("FDC_API_KEY", "").strip()
FORCE_GPT      = os.getenv("FORCE_GPT", "0").strip() in ("1","true","True")

USE_GPT_DEFAULT = bool(OPENAI_API_KEY) or FORCE_GPT
USE_FDC_DEFAULT = bool(FDC_API_KEY)
USE_OFF_DEFAULT = True  # OFF لا يحتاج مفتاح

APP_NAME = "Global Calorie & Nutrition Tracker"
APP_VERSION = "v1.7"

# =============== UI / PRIVACY ===============
st.set_page_config(page_title=APP_NAME, page_icon="🍽️", layout="centered")

# أخفي تفاصيل الأخطاء عن الزوار
st.set_option('client.showErrorDetails', False)
DEBUG = False  # خله True إذا تبي رسائل مطوّر داخل الصفحة

def _dev(msg):
    if DEBUG:
        st.info(str(msg))

st.markdown(f"""
<style>
:root {{
  --glass-bg: rgba(255,255,255,0.06);
  --glass-bd: rgba(255,255,255,0.12);
}}

/* NAVBAR */
.khalid-navbar {{
  position: fixed; top: 0; left: 0; right: 0; height: 56px; z-index: 10000;
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 18px; backdrop-filter: blur(8px);
  background: var(--glass-bg); border-bottom: 1px solid var(--glass-bd);
}}
.khalid-brand {{
  font-weight: 700; font-size: 15px; letter-spacing: .3px;
}}
.khalid-menu a {{
  margin-left: 14px; font-size: 13px; text-decoration: none;
  padding: 6px 10px; border: 1px solid var(--glass-bd); border-radius: 8px;
}}
.khalid-chip {{
  margin-left: 10px; font-size: 11px; opacity:.8; padding: 3px 8px;
  border: 1px solid var(--glass-bd); border-radius: 999px;
}}
/* دفع المحتوى للأسفل بسبب النافبار الثابت */
.block-container {{ padding-top: 76px; max-width: 980px; }}
input[type="text"]{{ border-radius: 10px !important; padding: 12px !important; }}
[data-baseweb="table"]{{ font-size: .95rem; }}
.card {{ padding:18px 20px;border-radius:16px;background:#111827;
        border:1px solid rgba(255,255,255,0.08); }}

/* حقوق خالد */
.khalid-top {{
  position: fixed; top: 62px; right: 18px; z-index: 9999;
  font-weight: 600; font-size: 14px; padding: 6px 10px;
  background: var(--glass-bg); border: 1px solid var(--glass-bd);
  border-radius: 10px; backdrop-filter: blur(6px);
}}
.khalid-bottom {{
  position: fixed; bottom: 10px; left: 18px; z-index: 9999;
  font-size: 13px; padding: 6px 10px; opacity: .85;
  background: var(--glass-bg); border: 1px solid var(--glass-bd);
  border-radius: 10px; backdrop-filter: blur(6px);
}}
@media (max-width: 600px){{
  .khalid-top, .khalid-bottom {{ font-size: 12px; }}
  .khalid-menu a {{ display:none; }}
}}
</style>

<!-- NAVBAR -->
<div class="khalid-navbar">
  <div class="khalid-brand">Khalid Al Muhairi <span class="khalid-chip">{APP_VERSION}</span></div>
  <div class="khalid-menu">
    <a href="#" title="About">About</a>
    <a href="#" title="Privacy">Privacy</a>
    <a href="#" title="Contact">Contact</a>
  </div>
</div>

<!-- RIGHTS BADGES -->
<div class="khalid-top">© 2025 Khalid Al Muhairi</div>
<div class="khalid-bottom">© ٢٠٢٥ خالد المهيري — جميع الحقوق محفوظة</div>
""", unsafe_allow_html=True)

# =============== LOCAL DB (with drinks) ===============
# وحدات: per100g / per100ml / perPiece
LOCAL_DB = {
    # Foods
    "oats": {"unit":"per100g","kcal":389,"p":16.9,"c":66.3,"f":6.9, "syn":["oat","شوفان"]},
    "low-fat milk": {"unit":"per100ml","kcal":45,"p":3.4,"c":4.9,"f":1.5, "syn":["milk","حليب"]},
    "egg": {"unit":"perPiece","kcal":78,"p":6.3,"c":0.6,"f":5.3, "syn":["eggs","بيض","بيضة"]},
    "chicken (skinless, cooked)": {"unit":"per100g","kcal":165,"p":31,"c":0,"f":3.6, "syn":["chicken","دجاج"]},

    # Drinks (per 100 ml)
    "water": {"unit":"per100ml","kcal":0,"p":0,"c":0,"f":0, "syn":["ماء","مويه","water"]},
    "cola": {"unit":"per100ml","kcal":42,"p":0,"c":10.6,"f":0, "syn":["coke","كوكاكولا","بيبسي"]},
    "cola zero": {"unit":"per100ml","kcal":1,"p":0,"c":0.1,"f":0, "syn":["diet cola","coke zero","بيبسي دايت"]},
    "orange juice": {"unit":"per100ml","kcal":45,"p":0.7,"c":10,"f":0.2, "syn":["عصير برتقال"]},
    "apple juice": {"unit":"per100ml","kcal":46,"p":0.1,"c":11.3,"f":0.1, "syn":["عصير تفاح"]},
    "mango juice": {"unit":"per100ml","kcal":60,"p":0.3,"c":15,"f":0.2, "syn":["عصير مانجو"]},
    "pomegranate juice": {"unit":"per100ml","kcal":54,"p":0.2,"c":13,"f":0.1, "syn":["عصير رمان"]},
    "lemonade": {"unit":"per100ml","kcal":40,"p":0.1,"c":10,"f":0, "syn":["ليمونادة","عصير ليمون"]},
    "sweet tea": {"unit":"per100ml","kcal":27,"p":0,"c":6.7,"f":0, "syn":["شاي محلى"]},
    "tea (unsweetened)": {"unit":"per100ml","kcal":1,"p":0,"c":0.2,"f":0, "syn":["شاي بدون سكر","tea"]},
    "coffee (black)": {"unit":"per100ml","kcal":2,"p":0.3,"c":0,"f":0, "syn":["قهوة","بلاك كوفي","أمريكانو"]},
    "latte": {"unit":"per100ml","kcal":45,"p":3.0,"c":4.8,"f":1.6, "syn":["لاتيه","latte"]},
    "cappuccino": {"unit":"per100ml","kcal":38,"p":3.0,"c":3.6,"f":1.3, "syn":["كابتشينو"]},
    "energy drink": {"unit":"per100ml","kcal":45,"p":0,"c":11,"f":0, "syn":["ريدبول","مونستر","energy"]},
    "sports drink": {"unit":"per100ml","kcal":25,"p":0,"c":6,"f":0, "syn":["مشروب رياضي","جاتوريد","باوريد"]},
    "whole milk": {"unit":"per100ml","kcal":61,"p":3.2,"c":4.7,"f":3.3, "syn":["حليب كامل"]},
    "skim milk": {"unit":"per100ml","kcal":34,"p":3.4,"c":5,"f":0.1, "syn":["حليب خالي الدسم"]},
    "chocolate milk": {"unit":"per100ml","kcal":77,"p":3.2,"c":11.5,"f":2.0, "syn":["حليب بالشوكولاتة"]},
}

def _find_local_key(name: str) -> Optional[str]:
    t = name.lower()
    for k, v in LOCAL_DB.items():
        if k in t: return k
        for s in v["syn"]:
            if s in t: return k
    return None

def local_nutrition(name: str, qty: float, unit: str):
    key = _find_local_key(name)
    if not key: return None
    item = LOCAL_DB[key]; u = item["unit"]
    if unit == "g" and u == "per100g": factor = qty/100.0
    elif unit == "ml" and u == "per100ml": factor = qty/100.0
    elif unit == "piece" and u == "perPiece": factor = qty
    else: return None
    kcal = round(item["kcal"]*factor,1)
    p = round(item["p"]*factor,1); c = round(item["c"]*factor,1); f = round(item["f"]*factor,1)
    return kcal,p,c,f,f"LocalDB ({key})"

# =============== PARSER (AR/EN) ===============
AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
def local_parse(txt: str) -> List[Dict]:
    t = (txt or "").strip().lower().translate(AR_DIGITS)
    t = t.replace("جرام","g").replace("جم","g").replace("غ","g").replace("مل","ml")
    t = t.replace("بيضة","egg").replace("بيض","eggs")
    if "half chicken" in t or "نصف دجاجة" in t:
        return [{"name":"chicken (skinless, cooked)","quantity":250.0,"unit":"g"}]
    if "quarter chicken" in t or "ربع دجاجة" in t:
        return [{"name":"chicken (skinless, cooked)","quantity":125.0,"unit":"g"}]
    m = re.match(r"(\d+(?:\.\d+)?)\s*g\s*(.*)", t)
    if m: return [{"name": (m.group(2) or "").strip() or "oats", "quantity": float(m.group(1)), "unit":"g"}]
    m = re.match(r"(\d+(?:\.\d+)?)\s*ml\s*(.*)", t)
    if m: return [{"name": (m.group(2) or "").strip() or "water", "quantity": float(m.group(1)), "unit":"ml"}]
    m = re.match(r"(\d+)\s*(eggs?|pieces?)", t)
    if m: return [{"name":"egg", "quantity": float(m.group(1)), "unit":"piece"}]
    return []

# =============== GPT (optional) ===============
OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
OA_HEADERS = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}

@dataclass
class Nutrition:
    kcal: float; protein: float; carbs: float; fat: float; source: str

def call_chat(messages, model="gpt-4o-mini", max_tokens=300, retries=2):
    if not OPENAI_API_KEY: return None
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0}
    last = None
    for i in range(retries+1):
        try:
            r = requests.post(OPENAI_CHAT_URL, headers=OA_HEADERS, json=body, timeout=30)
            if r.status_code in (429,500,503):
                time.sleep(1.3*(2**i)); last = r.text; continue
            if r.status_code != 200: return None
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            last = str(e); time.sleep(1.0*(i+1))
    return None

def gpt_extract_items(user_text: str) -> List[Dict]:
    sys = ("Output ONLY a JSON array: "
           "[{\"name\":str,\"quantity\":number,\"unit\":\"g\"|\"ml\"|\"piece\"}]. "
           "If Arabic, translate names to common English.")
    text = call_chat([{"role":"system","content":sys},{"role":"user","content":user_text}])
    if not text: return []
    m = re.search(r"\[.*\]", text, re.S)
    return json.loads(m.group(0)) if m else []

def gpt_nutrition(name: str, qty: float, unit: str) -> Optional[Nutrition]:
    prompt = (f"Give nutrition for {qty} {unit} {name}. "
              "Return ONLY JSON {{\"kcal\":n,\"protein\":n,\"carbs\":n,\"fat\":n}}.")
    text = call_chat([{"role":"user","content":prompt}], max_tokens=160)
    if not text: return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m: return None
    j = json.loads(m.group(0))
    try:
        return Nutrition(float(j["kcal"]), float(j["protein"]), float(j["carbs"]), float(j["fat"]), "GPT")
    except:
        return None

# =============== USDA FDC + OFF (cached dict) ===============
@st.cache_data(show_spinner=False)
def fdc_lookup(name: str, qty: float, unit: str):
    if not FDC_API_KEY: return None
    try:
        url = "https://api.nal.usda.gov/fdc/v1/foods/search"
        params = {
            "api_key": FDC_API_KEY, "query": name, "pageSize": 1,
            "dataType": "Survey (FNDDS),Branded,SR Legacy,Foundation"
        }
        s = requests.get(url, params=params, timeout=20).json()
        if not s.get("foods"): return None
        food = s["foods"][0]
        nutrients = {n.get("nutrientNumber"): n.get("value") for n in food.get("foodNutrients", [])}
        kcal100 = float(nutrients.get("1008") or 0)
        p100    = float(nutrients.get("1003") or 0)
        c100    = float(nutrients.get("1005") or 0)
        f100    = float(nutrients.get("1004") or 0)
        # ML≈g للمشروبات، وقطعة بيض ≈ 50g
        if unit == "piece" and "egg" in name.lower(): qty_g = qty*50.0
        elif unit == "ml": qty_g = qty*1.0
        else: qty_g = qty
        factor = qty_g/100.0
        return {"kcal": round(kcal100*factor,1), "protein": round(p100*factor,1),
                "carbs": round(c100*factor,1), "fat": round(f100*factor,1),
                "source": "USDA FDC"}
    except Exception as e:
        _dev(f"FDC error: {e}")
        return None

@st.cache_data(show_spinner=False)
def off_lookup(name: str, qty: float, unit: str):
    try:
        url = "https://world.openfoodfacts.org/cgi/search.pl"
        params = {"search_terms": name, "search_simple": 1, "json": 1, "action":"process", "page_size": 1}
        j = requests.get(url, params=params, timeout=20).json()
        prods = j.get("products") or []
        if not prods: return None
        p = prods[0].get("nutriments", {})
        kcal100 = float(p.get("energy-kcal_100g") or p.get("energy-kcal_100ml") or 0)
        prot100 = float(p.get("proteins_100g") or p.get("proteins_100ml") or 0)
        carbs100= float(p.get("carbohydrates_100g") or p.get("carbohydrates_100ml") or 0)
        fat100  = float(p.get("fat_100g") or p.get("fat_100ml") or 0)
        if unit == "piece" and "egg" in name.lower(): qty_g = qty*50.0
        elif unit == "ml": qty_g = qty*1.0
        else: qty_g = qty
        factor = qty_g/100.0
        return {"kcal": round(kcal100*factor,1), "protein": round(prot100*factor,1),
                "carbs": round(carbs100*factor,1), "fat": round(fat100*factor,1),
                "source": "OpenFoodFacts"}
    except Exception as e:
        _dev(f"OFF error: {e}")
        return None

# =============== SIDEBAR (nice extras) ===============
with st.sidebar:
    st.header("Khalid’s Panel")
    st.caption(f"Date: {date.today().isoformat()}")
    kcal_goal = st.number_input("Daily Calories Goal (kcal)", min_value=0, value=2000, step=50)
    show_sources = st.toggle("Show sources toggles", value=True)
    if show_sources:
        use_fdc = st.toggle("USDA FDC", value=USE_FDC_DEFAULT)
        use_off = st.toggle("Open Food Facts", value=USE_OFF_DEFAULT)
        use_gpt = st.toggle("ChatGPT", value=USE_GPT_DEFAULT)
    else:
        use_fdc, use_off, use_gpt = USE_FDC_DEFAULT, USE_OFF_DEFAULT, USE_GPT_DEFAULT
    if st.button("Clear log"):
        st.session_state.pop("rows", None)

# =============== HEADER CARD ===============
st.markdown(f"""
<div class="card">
  <h1 style="margin:0;font-size:28px;">🍽️ {APP_NAME}</h1>
  <p style="margin:6px 0 0;color:#9CA3AF;">Type any food or drink (AR/EN). We’ll fetch nutrition from global DBs.</p>
</div>
""", unsafe_allow_html=True)
st.write("")

# =============== STATE ===============
if "rows" not in st.session_state:
    st.session_state.rows = []

# =============== CORE ===============
def add_food_line(txt: str):
    # 1) Parse
    extracted = []
    if use_gpt and OPENAI_API_KEY:
        try:
            extracted = gpt_extract_items(txt)
        except Exception as e:
            _dev(f"GPT parse skipped: {e}")
    if not extracted:
        extracted = local_parse(txt)
    if not extracted:
        st.warning("Couldn’t parse that. Try: number + unit + food name.")
        return

    # 2) For each item: FDC -> OFF -> Local -> GPT (مع تجاهل النتائج الصفرية)
    for it in extracted:
        name, qty, unit = it["name"], float(it["quantity"]), it["unit"].lower()
        qty_str = str(int(qty)) if qty.is_integer() else str(qty)
        display = f"{qty_str} {unit} {name}"

        nut_obj: Optional[Nutrition] = None

        if USE_FDC_DEFAULT or use_fdc:
            d = fdc_lookup(name, qty, unit)
            if d and (d["kcal"] > 0 or d["protein"]+d["carbs"]+d["fat"] > 0):
                nut_obj = Nutrition(d["kcal"], d["protein"], d["carbs"], d["fat"], d["source"])

        if not nut_obj and (USE_OFF_DEFAULT or use_off):
            d = off_lookup(name, qty, unit)
            if d and (d["kcal"] > 0 or d["protein"]+d["carbs"]+d["fat"] > 0):
                nut_obj = Nutrition(d["kcal"], d["protein"], d["carbs"], d["fat"], d["source"])

        if not nut_obj:
            local = local_nutrition(name, qty, unit)
            if local:
                kcal,p,c,f,src = local
                if kcal > 0 or (p+c+f) > 0:
                    nut_obj = Nutrition(kcal,p,c,f,src)

        if not nut_obj and (USE_GPT_DEFAULT or use_gpt) and OPENAI_API_KEY:
            nut_obj = gpt_nutrition(name, qty, unit)

        if not nut_obj:
            st.error(f"No nutrition found for: {display}")
            continue

        st.session_state.rows.append({
            "Item": display,
            "kcal": float(nut_obj.kcal),
            "Protein (g)": float(nut_obj.protein),
            "Carbs (g)": float(nut_obj.carbs),
            "Fat (g)": float(nut_obj.fat),
            "Source": nut_obj.source
        })
    st.success("Added ✔")

def on_enter():
    txt = st.session_state.get("food_input","").strip()
    if not txt: 
        return
    add_food_line(txt)
    st.session_state["food_input"] = ""   # لا نستخدم st.rerun() — ستريملت يعيد التحديث تلقائيًا

# Input (auto on Enter)
st.text_input("Add food / drink", key="food_input",
              placeholder='e.g. "330 ml cola", "200 ml latte", "100 g oats" / "٣٣٠ مل كولا"',
              on_change=on_enter)

# Quick buttons (بدون st.rerun)
d1,d2,d3,d4,d5 = st.columns(5)
for col, txt in zip([d1,d2,d3,d4,d5],
                    ["250 ml water","330 ml cola","330 ml cola zero","250 ml orange juice","200 ml latte"]):
    if col.button(txt, use_container_width=True):
        add_food_line(txt)

# =============== TABLE / TOTALS / CHART ===============
if st.session_state.rows:
    df = pd.DataFrame(st.session_state.rows)
    st.subheader("Entries")
    st.dataframe(df[["Item","kcal","Protein (g)","Carbs (g)","Fat (g)","Source"]],
                 use_container_width=True, hide_index=True)

    tot = df[["kcal","Protein (g)","Carbs (g)","Fat (g)"]].sum(numeric_only=True).round(1)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Calories", f"{tot['kcal']} kcal / {kcal_goal} goal")
    c2.metric("Protein",  f"{tot['Protein (g)']} g")
    c3.metric("Carbs",    f"{tot['Carbs (g)']} g")
    c4.metric("Fat",      f"{tot['Fat (g)']} g")

    # Pie فقط إذا فيه قيم > 0 لتجنب ValueError
    p = float(tot.get("Protein (g)",0) or 0)
    c = float(tot.get("Carbs (g)",0) or 0)
    f = float(tot.get("Fat (g)",0) or 0)
    if (p + c + f) > 0:
        fig, ax = plt.subplots()
        ax.pie([p, c, f], labels=["Protein","Carbs","Fat"], autopct="%1.0f%%", startangle=90)
        ax.axis("equal")
        st.pyplot(fig)
    else:
        st.info("أضف عنصر فيه بروتين/كارب/دهون لعرض المخطط.")

    b1,b2,b3 = st.columns([1,1,2])
    if b1.button("Undo last"):
        if st.session_state.rows: st.session_state.rows.pop()
    if b2.button("Clear all"):
        st.session_state.rows.clear()
    with b3:
        st.download_button("Download CSV", df.to_csv(index=False).encode("utf-8"),
                           "log.csv", "text/csv")
else:
    st.info("No entries yet. Try quick buttons or type your own, then press Enter.")
