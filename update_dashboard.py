# -*- coding: utf-8 -*-
"""
Atualiza o dashboard com dados frescos do Garmin Connect.
Roda via GitHub Actions a cada hora.
Usa token OAuth salvo (GARMIN_TOKENS) para evitar bloqueio de IP.
"""
import os
import sys
import json
import datetime
from garminconnect import Garmin

# Força UTF-8 no terminal (Windows pode defaultar para cp1252)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKENS_JSON = os.environ.get("GARMIN_TOKENS")
EMAIL = os.environ.get("GARMIN_EMAIL", "")
PASSWORD = os.environ.get("GARMIN_PASSWORD", "")

client = Garmin(EMAIL, PASSWORD)

if TOKENS_JSON:
    # Usa token salvo — sem login interativo, evita bloqueio de IP
    client.client.loads(TOKENS_JSON)
    client._load_profile_and_settings()
    print("Autenticado via token salvo")
else:
    client.login()
    print("Autenticado via usuário/senha")

today = datetime.date.today().isoformat()
now_dt = datetime.datetime.now()
now = now_dt.strftime("%d/%m/%Y às %H:%Mh")
hora_atual = now_dt.hour  # hora local (Brasília via GitHub Actions = UTC-3... ajustar se necessário)

# Busca dados
stats = client.get_stats(today)
sleep_raw = client.get_sleep_data(today)
sleep = sleep_raw.get("dailySleepDTO", {})
scores = sleep.get("sleepScores", {})

try:
    hrv = client.get_hrv_data(today)
    hrv_val = hrv.get("hrvSummary", {}).get("lastNightAvg", "--")
    hrv_status = hrv.get("hrvSummary", {}).get("status", "--")
except Exception:
    hrv_val = "--"
    hrv_status = "--"

# Extrai valores
body_battery = stats.get("bodyBatteryMostRecentValue", "--")
bb_max = stats.get("bodyBatteryHighestValue", "--")
bb_min = stats.get("bodyBatteryLowestValue", "--")
steps = stats.get("totalSteps", 0)
steps_goal = stats.get("dailyStepGoal", 9000)
steps_pct = round((steps / steps_goal) * 100) if steps_goal else 0
fc_repouso = stats.get("restingHeartRate", "--")
estresse = stats.get("averageStressLevel", "--")
spo2_min = stats.get("lowestSpo2", "--")
spo2_media = stats.get("averageSpo2", "--")
calorias = stats.get("activeKilocalories", "--")

sono_h = round(sleep.get("sleepTimeSeconds", 0) / 3600, 1)
sono_score = scores.get("overall", {}).get("value", "--")
sono_qualidade = scores.get("overall", {}).get("qualifierKey", "--")
sono_profundo = round(sleep.get("deepSleepSeconds", 0) / 60)
sono_rem = round(sleep.get("remSleepSeconds", 0) / 60)
sono_leve = round(sleep.get("lightSleepSeconds", 0) / 60)
acordou = sleep.get("awakeCount", "--")
spo2_sono = sleep.get("averageSpO2Value", "--")
spo2_sono_min = sleep.get("lowestSpO2Value", "--")

# Determina feedbacks automáticos
def bb_feedback(val):
    if val == "--": return ("yellow", "⚡ Sem dado")
    if val < 25: return ("red", "🔴 Crítico — só recuperação hoje")
    if val < 40: return ("red", "⚠️ Baixo — treino leve")
    if val < 60: return ("yellow", "⚡ Moderado — cuidado na intensidade")
    return ("green", "✅ Bom — pode treinar")

def sono_feedback(score):
    if score == "--": return ("yellow", "⚡ Sem dado")
    if score < 50: return ("red", "⚠️ Sono ruim — priorize recuperação")
    if score < 70: return ("yellow", "⚡ Sono regular — atenção à intensidade")
    if score < 85: return ("green", "✅ Sono bom")
    return ("green", "✅ Sono excelente")

def spo2_feedback(val):
    if val == "--": return ("yellow", "⚡ Sem dado")
    if val < 88: return ("red", "🔴 Crítico — investigar")
    if val < 90: return ("red", "⚠️ Abaixo de 90% — atenção")
    if val < 94: return ("yellow", "⚡ Levemente baixo")
    return ("green", "✅ Normal")

def fc_feedback(val):
    if val == "--": return ("yellow", "⚡ Sem dado")
    if val < 60: return ("green", "✅ Excelente")
    if val < 70: return ("green", "✅ Saudável")
    if val < 80: return ("yellow", "⚡ Atenção")
    return ("red", "⚠️ Elevada")

def steps_feedback(pct):
    if pct >= 100: return ("green", "✅ Meta batida!")
    if pct >= 60: return ("yellow", "⚡ Bom progresso")
    if pct >= 30: return ("yellow", "⚡ Continue se movendo")
    return ("red", "⚠️ Muito parada hoje")

# Determina orientação do dia
bb_cor, bb_msg = bb_feedback(body_battery if body_battery != "--" else 0)
sono_cor, sono_msg = sono_feedback(sono_score if sono_score != "--" else 0)

if (body_battery != "--" and body_battery < 25) or (sono_score != "--" and sono_score < 50):
    orientacao_cor = "red"
    orientacao_icon = "😴"
    orientacao_titulo = "Dia de descanso ativo"
    orientacao_texto = "Body Battery ou sono muito baixos. Bike leve 20–30 min · FC abaixo de 120 · Sem musculação pesada hoje."
elif (body_battery != "--" and body_battery < 45) or (sono_score != "--" and sono_score < 65):
    orientacao_cor = "yellow"
    orientacao_icon = "⚠️"
    orientacao_titulo = "Treino moderado — sem forçar"
    orientacao_texto = "Sinais de recuperação incompleta. Musculação com carga reduzida · Cardio zona 2 · Sem corrida forte hoje."
else:
    orientacao_cor = "green"
    orientacao_icon = "💪"
    orientacao_titulo = "Pode treinar! Siga a ficha do dia."
    orientacao_texto = "Body Battery e sono em bom nível. Siga a ficha semanal normalmente. Monitore a FC durante o treino."

# Frase do Claude sobre o sono
rem_pct = round((sleep.get("remSleepSeconds", 0) / max(sleep.get("sleepTimeSeconds", 1), 1)) * 100)

if sono_score != "--" and sono_score >= 80:
    frase_sono = f"Boa noite de sono! Você dormiu {sono_h}h com score {sono_score} — seu corpo recuperou bem. Aproveite o dia."
elif sono_score != "--" and sono_score >= 65:
    frase_sono = f"Noite razoável — {sono_h}h dormidas, score {sono_score}. Deu pra recuperar mas não foi o ideal. Atenção à intensidade hoje."
elif sono_score != "--":
    frase_sono = f"Noite difícil: apenas {sono_h}h com score {sono_score} e {sono_rem} min de REM ({rem_pct}%). Seu corpo não recuperou de verdade — hoje é dia de poupar energia."
else:
    frase_sono = "Não foi possível ler os dados de sono desta noite."

# ── Verifica se já fez atividade hoje ─────────────────────────────────────────
# ✏️ PERSONALIZAR: plano semanal — nomes devem bater com a ficha em index.html (Treino A..F)
# 0=Segunda … 6=Domingo · lembrar_apos = hora BRT para alertar se não treinou
PLANO_SEMANA = {
    0: {"nome": "Treino A",           "tipo": "musculacao", "lembrar_apos": 17},  # Segunda
    1: {"nome": "Treino B",           "tipo": "musculacao", "lembrar_apos": 17},  # Terça
    2: {"nome": "Treino C",           "tipo": "musculacao", "lembrar_apos": 17},  # Quarta
    3: {"nome": "Treino D",           "tipo": "musculacao", "lembrar_apos": 17},  # Quinta
    4: {"nome": "Treino E",           "tipo": "musculacao", "lembrar_apos": 17},  # Sexta
    5: {"nome": "Descanso ativo",     "tipo": "bike",       "lembrar_apos": 15},  # Sábado
    6: {"nome": "Treino F",           "tipo": "musculacao", "lembrar_apos": 15},  # Domingo
}

dia_semana = now_dt.weekday()  # 0=segunda … 6=domingo
treino_hoje = PLANO_SEMANA.get(dia_semana, {})
treino_nome_hoje = treino_hoje.get("nome", "")
lembrar_apos = treino_hoje.get("lembrar_apos", 17)

# Hora de Brasília = UTC-3 (GitHub Actions roda em UTC)
hora_brasilia = hora_atual - 3  # ajuste simples; em produção usar pytz se necessário

atividade_feita = False
cardio_feito = False
musculacao_feita = False
minutos_ativos_hoje = 0

try:
    atividades_hoje = client.get_activities_by_date(today, today, activitytype=None)
    for a in atividades_hoje:
        tipo = (a.get("activityType", {}).get("typeKey") or "").lower()
        duracao = a.get("duration", 0) or 0
        if duracao > 300:  # mais de 5 min conta
            atividade_feita = True
            minutos_ativos_hoje += round(duracao / 60)
            if any(k in tipo for k in ["cycling", "bike", "indoor_cycling"]):
                cardio_feito = True
            if any(k in tipo for k in ["strength", "fitness_equipment", "cardio"]):
                musculacao_feita = True
    print(f"   Atividades hoje: {len(atividades_hoje)} | musculação={musculacao_feita} | bike={cardio_feito}")
except Exception as e:
    print(f"   Aviso: não foi possível buscar atividades de hoje — {e}")

# Define alerta de treino
alerta_treino = ""
alerta_treino_urgente = False

if hora_brasilia >= lembrar_apos:
    tipo_esperado = treino_hoje.get("tipo", "")
    if tipo_esperado == "bike" and not cardio_feito and not atividade_feita:
        alerta_treino = "Ainda não fez a bike hoje! Vai lá — 20 a 30 minutos, FC abaixo de 130 bpm. Você consegue 💪"
        alerta_treino_urgente = hora_brasilia >= 20
    elif tipo_esperado == "musculacao" and not musculacao_feita and not atividade_feita:
        alerta_treino = f"Treino de hoje: {treino_nome_hoje}. Você ainda não registrou nenhuma atividade. Vai treinar hoje?"
        alerta_treino_urgente = hora_brasilia >= 20

# Gera o data.js
data = {
    "atualizado": now,
    "hoje": today,
    "body_battery": body_battery,
    "bb_max": bb_max,
    "bb_min": bb_min,
    "bb_feedback_cor": bb_cor,
    "bb_feedback_msg": bb_msg,
    "steps": f"{steps:,.0f}".replace(",", "."),
    "steps_goal": f"{steps_goal:,.0f}".replace(",", "."),
    "steps_pct": steps_pct,
    "steps_feedback_cor": steps_feedback(steps_pct)[0],
    "steps_feedback_msg": steps_feedback(steps_pct)[1],
    "fc_repouso": fc_repouso,
    "fc_feedback_cor": fc_feedback(fc_repouso if fc_repouso != "--" else 70)[0],
    "fc_feedback_msg": fc_feedback(fc_repouso if fc_repouso != "--" else 70)[1],
    "estresse": estresse,
    "spo2_min": spo2_min,
    "spo2_media": spo2_media,
    "spo2_feedback_cor": spo2_feedback(spo2_min if spo2_min != "--" else 95)[0],
    "spo2_feedback_msg": spo2_feedback(spo2_min if spo2_min != "--" else 95)[1],
    "hrv_val": hrv_val,
    "hrv_status": hrv_status,
    "calorias": calorias,
    "sono_h": sono_h,
    "sono_score": sono_score,
    "sono_qualidade": sono_qualidade,
    "sono_profundo": sono_profundo,
    "sono_rem": sono_rem,
    "sono_leve": sono_leve,
    "acordou": acordou,
    "spo2_sono": spo2_sono,
    "spo2_sono_min": spo2_sono_min,
    "sono_feedback_cor": sono_cor,
    "sono_feedback_msg": sono_msg,
    "frase_sono": frase_sono,
    "orientacao_cor": orientacao_cor,
    "orientacao_icon": orientacao_icon,
    "orientacao_titulo": orientacao_titulo,
    "orientacao_texto": orientacao_texto,
    "treino_nome_hoje": treino_nome_hoje,
    "atividade_feita": atividade_feita,
    "cardio_feito": cardio_feito,
    "musculacao_feita": musculacao_feita,
    "minutos_ativos_hoje": minutos_ativos_hoje,
    "alerta_treino": alerta_treino,
    "alerta_treino_urgente": alerta_treino_urgente,
    "hora_brasilia": hora_brasilia,
}

with open("data.js", "w", encoding="utf-8") as f:
    f.write(f"const GARMIN = {json.dumps(data, ensure_ascii=False, indent=2)};\n")

print(f"✅ Dashboard atualizado em {now}")
print(f"   Body Battery: {body_battery} | Sono: {sono_h}h score {sono_score} | Passos: {steps}")
