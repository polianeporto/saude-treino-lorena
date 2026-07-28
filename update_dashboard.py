# -*- coding: utf-8 -*-
"""
Atualiza o dashboard com dados frescos do Garmin Connect.
Roda via GitHub Actions a cada hora.
Usa token OAuth salvo (GARMIN_TOKENS) para evitar bloqueio de IP.
"""
import os
import re
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

# O GitHub Actions roda em UTC — usamos um fuso fixo de Brasília (UTC-3, sem
# horário de verão desde 2019) para que data, dia da semana e hora batam com
# o horário real dela, inclusive perto da meia-noite.
BRASILIA_TZ = datetime.timezone(datetime.timedelta(hours=-3))
now_dt = datetime.datetime.now(BRASILIA_TZ)
today = now_dt.date().isoformat()
now = now_dt.strftime("%d/%m/%Y às %H:%Mh")
hora_atual = now_dt.hour  # já em horário de Brasília

# ── Envio dos treinos para o Garmin Connect ────────────────────────────────
# Protocolo real (Coach Allan Vieira / AV Team). Cada item: (exercício, séries, repetições, descanso)
TREINOS_EXERCICIOS = {
    "A": [
        ("Cadeira extensora (pico de contração 2s + drop-set na última série)", "4X", "15/10/10/10", "1M"),
        ("Leg press 45° (priorizar boa amplitude)", "3X", "12 A 15", "2M"),
        ("Agachamento no Hack (descer até o talo)", "4X", "15/10/10/10", "1M"),
        ("Cadeira flexora (pico de contração 3s nas 8 primeiras reps)", "4X", "12 A 15", "1M"),
        ("Mesa flexora (drop-set)", "2X", "10.10.10", "2M"),
        ("Cadeira adutora", "4X", "12 A 15", "1M"),
    ],
    "B": [
        ("Desenvolvimento na máquina", "4X", "12 A 15", "40S"),
        ("Elevação lateral com halteres", "6X", "15", "30S"),
        ("Crucifixo inverso no voador, peg. pronada", "3X", "12 A 15", "40S"),
        ("Remada baixa peg. pronada aberta", "4X", "15/12/10/10", "1M"),
        ("Remada baixa peg. neutra com triângulo", "3X", "12 A 15", "40S"),
        ("Pulley frente peg. pronada aberta", "3X", "12 A 15", "40S"),
        ("Face pull com a corda", "4X", "12 A 15", "40S"),
    ],
    "C": [
        ("Cadeira abdutora em 45° (ativação)", "5X", "15", "1M"),
        ("Abdução de quadril cruzado no cross over", "4X", "12", "1M"),
        ("Elevação pélvica", "5X", "15/15/10/10/10", "2M"),
        ("Terra sumô (carga máx)", "4X", "15/10/10/10", "2M"),
        ("Afundo no Smith (descer até o talo)", "3X", "12", "2M"),
        ("Stiff com os pés abduzidos", "4X", "15/10/10/10", "2M"),
    ],
}
NOMES_TREINO = {
    "A": "Treino A - MMII Coxa completa",
    "B": "Treino B - MMSS Superior completo",
    "C": "Treino C - MMII Gluteo e posterior",
}


def _parse_int(texto, default):
    m = re.search(r"\d+", str(texto))
    return int(m.group()) if m else default


def _parse_descanso_segundos(texto):
    t = str(texto).upper().strip()
    n = _parse_int(t, 60)
    return n * 60 if "M" in t else n


def build_strength_workout(nome_treino, exercicios):
    """Monta o JSON de um treino de força no formato aceito pela API do Garmin Connect."""
    counter = [1]

    def nxt():
        v = counter[0]
        counter[0] += 1
        return v

    steps = []
    for ex_nome, series_txt, reps_txt, descanso_txt in exercicios:
        series = _parse_int(series_txt, 1)
        reps_alvo = _parse_int(reps_txt, 12)
        descanso_seg = _parse_descanso_segundos(descanso_txt)
        repeat_order = nxt()
        main_step = {
            "type": "ExecutableStepDTO",
            "stepOrder": nxt(),
            "stepType": {"stepTypeId": 8, "stepTypeKey": "main", "displayOrder": 8},
            "endCondition": {"conditionTypeId": 10, "conditionTypeKey": "reps", "displayOrder": 10, "displayable": True},
            "endConditionValue": reps_alvo,
            "targetType": {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1},
            "description": f"{ex_nome} - {series_txt} x {reps_txt}",
        }
        rest_step = {
            "type": "ExecutableStepDTO",
            "stepOrder": nxt(),
            "stepType": {"stepTypeId": 5, "stepTypeKey": "rest", "displayOrder": 5},
            "endCondition": {"conditionTypeId": 8, "conditionTypeKey": "fixed.rest", "displayOrder": 8, "displayable": True},
            "endConditionValue": descanso_seg,
            "targetType": {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1},
        }
        steps.append({
            "type": "RepeatGroupDTO",
            "stepOrder": repeat_order,
            "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6},
            "numberOfIterations": series,
            "workoutSteps": [main_step, rest_step],
            "endCondition": {"conditionTypeId": 7, "conditionTypeKey": "iterations", "displayOrder": 7, "displayable": False},
            "endConditionValue": float(series),
            "smartRepeat": False,
        })

    return {
        "workoutName": nome_treino,
        "sportType": {"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 5},
        "estimatedDurationInSecs": 2700,
        "workoutSegments": [{
            "segmentOrder": 1,
            "sportType": {"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 5},
            "workoutSteps": steps,
        }],
        "description": "Protocolo Coach Allan Vieira (AV Team) - gerado automaticamente",
    }


def ensure_workouts_no_garmin(client):
    """Garante que os treinos A/B/C existam na biblioteca de treinos do Garmin da aluna
    (cria só na primeira vez; nas próximas execuções reaproveita os já existentes)."""
    ids = {}
    try:
        existentes = client.get_workouts(limit=200) or []
        por_nome = {w.get("workoutName"): w.get("workoutId") for w in existentes if isinstance(w, dict)}
    except Exception as e:
        print(f"   Aviso: não foi possível listar treinos do Garmin — {e}")
        return ids

    for letra, nome in NOMES_TREINO.items():
        if nome in por_nome:
            ids[letra] = por_nome[nome]
            continue
        try:
            payload = build_strength_workout(nome, TREINOS_EXERCICIOS[letra])
            resultado = client.upload_workout(payload)
            wid = resultado.get("workoutId") if isinstance(resultado, dict) else None
            if wid:
                ids[letra] = wid
                print(f"   Treino '{nome}' criado no Garmin (id {wid})")
        except Exception as e:
            print(f"   Aviso: falha ao criar treino '{nome}' no Garmin — {e}")

    return ids


def safe_get(d, key, default):
    """Como d.get(key, default), mas também troca None por default
    (o Garmin às vezes retorna a chave presente com valor null, não ausente)."""
    v = d.get(key, default)
    return default if v is None else v

# Busca dados
stats = client.get_stats(today)
sleep_raw = client.get_sleep_data(today)
sleep = sleep_raw.get("dailySleepDTO", {}) or {}
scores = sleep.get("sleepScores", {}) or {}

try:
    hrv = client.get_hrv_data(today)
    hrv_summary = (hrv or {}).get("hrvSummary", {}) or {}
    hrv_val = safe_get(hrv_summary, "lastNightAvg", "--")
    hrv_status = safe_get(hrv_summary, "status", "--")
except Exception:
    hrv_val = "--"
    hrv_status = "--"

# Extrai valores
body_battery = safe_get(stats, "bodyBatteryMostRecentValue", "--")
bb_max = safe_get(stats, "bodyBatteryHighestValue", "--")
bb_min = safe_get(stats, "bodyBatteryLowestValue", "--")
steps = safe_get(stats, "totalSteps", 0)
steps_goal = safe_get(stats, "dailyStepGoal", 9000)
steps_pct = round((steps / steps_goal) * 100) if steps_goal else 0
fc_repouso = safe_get(stats, "restingHeartRate", "--")
estresse = safe_get(stats, "averageStressLevel", "--")
spo2_min = safe_get(stats, "lowestSpo2", "--")
spo2_media = safe_get(stats, "averageSpo2", "--")
calorias = safe_get(stats, "activeKilocalories", "--")

sono_h = round(safe_get(sleep, "sleepTimeSeconds", 0) / 3600, 1)
overall_score = scores.get("overall", {}) or {}
sono_score = safe_get(overall_score, "value", "--")
sono_qualidade = safe_get(overall_score, "qualifierKey", "--")
sono_profundo = round(safe_get(sleep, "deepSleepSeconds", 0) / 60)
sono_rem = round(safe_get(sleep, "remSleepSeconds", 0) / 60)
sono_leve = round(safe_get(sleep, "lightSleepSeconds", 0) / 60)
acordou = safe_get(sleep, "awakeCount", "--")
spo2_sono = safe_get(sleep, "averageSpO2Value", "--")
spo2_sono_min = safe_get(sleep, "lowestSpO2Value", "--")

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
rem_pct = round((safe_get(sleep, "remSleepSeconds", 0) / max(safe_get(sleep, "sleepTimeSeconds", 1), 1)) * 100)

if sono_score != "--" and sono_score >= 80:
    frase_sono = f"Boa noite de sono! Você dormiu {sono_h}h com score {sono_score} — seu corpo recuperou bem. Aproveite o dia."
elif sono_score != "--" and sono_score >= 65:
    frase_sono = f"Noite razoável — {sono_h}h dormidas, score {sono_score}. Deu pra recuperar mas não foi o ideal. Atenção à intensidade hoje."
elif sono_score != "--":
    frase_sono = f"Noite difícil: apenas {sono_h}h com score {sono_score} e {sono_rem} min de REM ({rem_pct}%). Seu corpo não recuperou de verdade — hoje é dia de poupar energia."
else:
    frase_sono = "Não foi possível ler os dados de sono desta noite."

# ── Verifica se já fez atividade hoje ─────────────────────────────────────────
# Protocolo real (Coach Allan Vieira / AV Team): sistema A/B/C alternado em ciclo de 2 semanas.
# Nomes devem bater com a ficha em index.html. 0=Segunda … 6=Domingo.
TREINOS = {
    "A":   {"nome": "Treino A — MMII Coxa completa",        "tipo": "musculacao"},
    "B":   {"nome": "Treino B — MMSS Superior completo",    "tipo": "musculacao"},
    "C":   {"nome": "Treino C — MMII Glúteo e posterior",   "tipo": "musculacao"},
    "OFF": {"nome": "Descanso — só cardio",                 "tipo": "cardio"},
}
SEMANA_1 = {0: "A", 1: "B", 2: "C", 3: "B", 4: "A", 5: "OFF", 6: "OFF"}
SEMANA_2 = {0: "C", 1: "B", 2: "A", 3: "B", 4: "C", 5: "OFF", 6: "OFF"}

# ✏️ Ajustar se a semana 1/2 real não bater: aqui uso a paridade da semana ISO do ano
# (semanas ímpares = Semana 1, pares = Semana 2) como referência simples e estável.
semana_do_ano = now_dt.isocalendar()[1]
padrao_semana = SEMANA_1 if semana_do_ano % 2 == 1 else SEMANA_2

dia_semana = now_dt.weekday()  # 0=segunda … 6=domingo
letra_hoje = padrao_semana.get(dia_semana, "OFF")
treino_hoje = TREINOS[letra_hoje]
treino_nome_hoje = treino_hoje.get("nome", "")
tipo_esperado_hoje = treino_hoje.get("tipo", "")
# Cardio (esteira/escada) é diário, então o lembrete é sempre depois do treino/musculação
lembrar_apos = 17 if tipo_esperado_hoje == "musculacao" else 15

# Lê o data.js da execução anterior — usado para (1) saber se o treino de hoje já
# foi agendado no Garmin e (2) montar a comparação automática "comparado com ontem"
workout_agendado_data = None
_dados_anteriores = None
try:
    with open("data.js", encoding="utf-8") as f:
        _conteudo_anterior = f.read()
    _prefixo = "const GARMIN = "
    if _conteudo_anterior.startswith(_prefixo):
        _dados_anteriores = json.loads(_conteudo_anterior[len(_prefixo):].rstrip("\n;"))
        workout_agendado_data = _dados_anteriores.get("workout_agendado_data")
except Exception:
    workout_agendado_data = None
    _dados_anteriores = None

# Envia (uma vez) e agenda (uma vez por dia) o treino de força no Garmin Connect
if letra_hoje in NOMES_TREINO and workout_agendado_data != today:
    try:
        workout_ids = ensure_workouts_no_garmin(client)
        wid = workout_ids.get(letra_hoje)
        if wid:
            client.schedule_workout(wid, today)
            workout_agendado_data = today
            print(f"   Treino {letra_hoje} agendado no calendário do Garmin para {today}")
    except Exception as e:
        print(f"   Aviso: não foi possível agendar o treino no Garmin — {e}")

# ── Comparação automática "comparado com ontem" ─────────────────────────────
# Guarda um retrato dos números de ontem (métricas, não os textos) para comparar
# com hoje. Só troca o retrato quando o dia muda de fato — assim, mesmo rodando
# várias vezes no mesmo dia, a comparação continua sendo "hoje vs. ontem" e não
# "agora vs. a última execução de há uma hora".
CAMPOS_COMPARAVEIS = ["body_battery", "sono_h", "sono_score", "fc_repouso", "steps", "estresse"]
ontem_snapshot = None
if _dados_anteriores:
    if _dados_anteriores.get("hoje") != today:
        # virou o dia: o que tínhamos até agora passa a ser o retrato de "ontem"
        ontem_snapshot = {c: _dados_anteriores.get(c) for c in CAMPOS_COMPARAVEIS}
    else:
        # ainda é hoje: mantém o retrato de ontem que já estava salvo
        ontem_snapshot = _dados_anteriores.get("ontem_snapshot")


def _comparar_metrica(nome, valor_hoje, valor_ontem, unidade="", pior_se_maior=False):
    try:
        h = float(valor_hoje)
        o = float(valor_ontem)
    except (TypeError, ValueError):
        return None
    if h == o:
        return f"• {nome}: estável em {valor_hoje}{unidade}"
    subiu = h > o
    melhorou = (not subiu) if pior_se_maior else subiu
    seta = "📈" if subiu else "📉"
    palavra = "melhorou" if melhorou else "piorou"
    return f"• {nome}: {seta} de {valor_ontem} para {valor_hoje}{unidade} ({palavra} em relação a ontem)"


if ontem_snapshot:
    linhas = [
        _comparar_metrica("Body Battery", body_battery, ontem_snapshot.get("body_battery")),
        _comparar_metrica("Sono", sono_h, ontem_snapshot.get("sono_h"), "h"),
        _comparar_metrica("Score do sono", sono_score, ontem_snapshot.get("sono_score")),
        _comparar_metrica("FC repouso", fc_repouso, ontem_snapshot.get("fc_repouso"), " bpm", pior_se_maior=True),
        _comparar_metrica("Passos", steps, ontem_snapshot.get("steps")),
        _comparar_metrica("Estresse", estresse, ontem_snapshot.get("estresse"), pior_se_maior=True),
    ]
    linhas = [l for l in linhas if l]
    analise_diaria = "\n".join(linhas) if linhas else "Ainda não há dados suficientes de ontem para comparar."
else:
    analise_diaria = "Ainda não há dados de ontem para comparar — a partir de amanhã essa análise aparece aqui."

hora_brasilia = hora_atual  # now_dt já está em horário de Brasília (ver BRASILIA_TZ acima)

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
            # Ela não corre — cardio é esteira (caminhada/corrida leve na esteira) ou escada/stepper
            if any(k in tipo for k in ["walking", "treadmill", "stair", "elliptical", "indoor_walking"]):
                cardio_feito = True
            if any(k in tipo for k in ["strength", "fitness_equipment"]):
                musculacao_feita = True
    print(f"   Atividades hoje: {len(atividades_hoje)} | musculação={musculacao_feita} | cardio={cardio_feito}")
except Exception as e:
    print(f"   Aviso: não foi possível buscar atividades de hoje — {e}")

# Define alerta de treino
alerta_treino = ""
alerta_treino_urgente = False

if hora_brasilia >= lembrar_apos:
    if tipo_esperado_hoje == "cardio" and not cardio_feito and not atividade_feita:
        alerta_treino = "Ainda não fez o cardio de hoje (60 min esteira/escada)! Vai lá 💪"
        alerta_treino_urgente = hora_brasilia >= 20
    elif tipo_esperado_hoje == "musculacao" and not musculacao_feita and not atividade_feita:
        alerta_treino = f"Treino de hoje: {treino_nome_hoje}. Você ainda não registrou nenhuma atividade. Vai treinar hoje?"
        alerta_treino_urgente = hora_brasilia >= 20

# ── Resumo para o personal ──────────────────────────────────────────────────
# Texto pronto para copiar e enviar ao coach, gerado toda vez que os dados são
# atualizados (inclusive quando ela clica em "Atualizar" no dashboard).
_fc_ref = fc_repouso if fc_repouso != "--" else 70
_spo2_ref = spo2_min if spo2_min != "--" else 95
_fc_cor, _fc_msg = fc_feedback(_fc_ref)
_spo2_cor, _spo2_msg = spo2_feedback(_spo2_ref)
_steps_cor, _steps_msg = steps_feedback(steps_pct)

resumo_personal = f"""📋 Resumo diário — Lorena Almeida ({now})

🏋️ Treino do dia: {treino_nome_hoje}
Musculação: {"✅ feita" if musculacao_feita else "❌ ainda não registrada"}
Cardio (esteira/escada): {"✅ feito" if cardio_feito else "❌ ainda não registrado"}{f" — {minutos_ativos_hoje} min de atividade hoje" if minutos_ativos_hoje else ""}

⚡ Body Battery: {body_battery}/100 — {bb_msg}
😴 Sono: {sono_h}h · score {sono_score} — {sono_msg}
❤️ FC repouso: {fc_repouso} bpm — {_fc_msg}
🚶 Passos: {steps}/{steps_goal} ({steps_pct}%) — {_steps_msg}
🫁 SpO2 mínimo: {spo2_min}% — {_spo2_msg}
📊 Estresse médio: {estresse}/100
🔋 HRV: {hrv_val} ({hrv_status})

Orientação automática: {orientacao_titulo} — {orientacao_texto}"""

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
    "resumo_personal": resumo_personal,
    "workout_agendado_data": workout_agendado_data,
    "analise_diaria": analise_diaria,
    "ontem_snapshot": ontem_snapshot,
}

with open("data.js", "w", encoding="utf-8") as f:
    f.write(f"const GARMIN = {json.dumps(data, ensure_ascii=False, indent=2)};\n")

print(f"✅ Dashboard atualizado em {now}")
print(f"   Body Battery: {body_battery} | Sono: {sono_h}h score {sono_score} | Passos: {steps}")
