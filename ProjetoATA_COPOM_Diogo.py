from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.firefox.service import Service
import geckodriver_autoinstaller
import csv
import os
from google import genai
import streamlit as st
from datetime import datetime

# ——— 1) Configuração inicial Streamlit — DEVE VIR PRIMEIRO ———
st.set_page_config(
    page_title="Analisador de Atas do COPOM",
    layout="centered",
)

# ——— 2) Configuração da API Gemini e instância do modelo ———
client = genai.Client(api_key = 'AIzaSyDcrdoaOqpo8QGn8Vwxvt4TmZ8Uok0ki9A')

def chamarModelo(prompt: str):
    return client.models.generate_content(
        model="gemini-2.5-pro",
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            thinking_config=genai.types.ThinkingConfig(thinking_budget=-1)  # ativa pensamento dinâmico
        )
    )

# ——— 3) Caminhos de CSV ———
CSV_PATH = 'ata_copom.csv'
TEMP_CSV = 'ata_copom_temp.csv'

# ——— 4) Funções auxiliares — scraping, CSV e IA ———

def get_new_driver():
    # Instala automaticamente a versão compatível do geckodriver
    geckodriver_autoinstaller.install()

    service = Service(
        executable_path=geckodriver_autoinstaller.install(),
        log_path='geckodriver.log'
    )
    options = webdriver.FirefoxOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    return webdriver.Firefox(service=service, options=options)

def get_element_by_xpath(driver, xpath: str):
    try:
        return WebDriverWait(driver, 30).until(
            ec.presence_of_element_located((By.XPATH, xpath))
        )
    except TimeoutException:
        return None

def pegar_nova_ata():
    driver = get_new_driver()
    driver.get('https://www.bcb.gov.br/publicacoes/atascopom/cronologicos')
    link_el = get_element_by_xpath(
        driver,
        '/html/body/app-root/app-root/div/div/main/dynamic-comp/div/div/'
        'bcb-publicacao/div/div/bcb-ultimaspublicacoes/div/div[1]/div[2]/h4/a'
    )
    link = link_el.get_attribute("href") if link_el else None
    return link, driver

def pegar_conteudo_nova_ata(link, driver=None):
    if not driver:
        driver = get_new_driver()
    driver.get(link)
    content_el = get_element_by_xpath(
        driver,
        "/html/body/app-root/app-root/div/div/main/dynamic-comp/div/div/" 
        "bcb-publicacao/div/div[1]/div/div/div/div[3]/div/div/div[1]"
    )
    return content_el.text if content_el else ""

def resumo_ja_existe(link):
    if not os.path.exists(CSV_PATH):
        return False
    with open(CSV_PATH, encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f, delimiter=';'):
            if row.get('url') == link and row.get('resumo', '').strip():
                return True
    return False

def gerar_resumo(texto):
    prompt = (
        "Você é um analista sênior de mercado financeiro especializado em política monetária brasileira.\n\n"
        "Receba abaixo o texto integral de uma ata recente do COPOM e produza uma avaliação técnica.\n"
        "Organize sua resposta em bullet points contemplando:\n"
        "1. Principais pontos da conjuntura econômica nacional e internacional;\n"
        "2. Comentários sobre inflação, atividade econômica, expectativas e postura do BC;\n"
        "3. Indícios sobre a trajetória futura da Selic, com justificativas técnicas;\n"
        "4. Projeção fundamentada (cenário base) para a próxima decisão de juros.\n\n"
        f"{texto}"
    )
    response = chamarModelo(prompt)
    return response.text.strip()

def atualizar_csv_com_resumo(link, conteudo, resumo):
    fieldnames = ['url', 'conteudo', 'resumo']
    atualizado = False

    # Verifica se o CSV original existe
    if os.path.exists(CSV_PATH):
        # Copia e atualiza dados do CSV original para o temporário
        with open(CSV_PATH, 'r', encoding='utf-8', newline='') as rf, \
             open(TEMP_CSV, 'w', encoding='utf-8', newline='') as wf:

            reader = csv.DictReader(rf, delimiter=';')
            writer = csv.DictWriter(wf, fieldnames=fieldnames, delimiter=';')
            writer.writeheader()

            for row in reader:
                if 'url' not in row:
                    print("⚠️ Linha sem a chave 'url':", row)
                    continue

                if row['url'] == link:
                    row['resumo'] = resumo
                    atualizado = True

                writer.writerow(row)

        # Se o link não foi atualizado (ou seja, é novo), adiciona ao final
        if not atualizado:
            with open(TEMP_CSV, 'a', encoding='utf-8', newline='') as wf:
                writer = csv.DictWriter(wf, fieldnames=fieldnames, delimiter=';')
                writer.writerow({'url': link, 'conteudo': conteudo, 'resumo': resumo})
    else:
        # Se o CSV não existe, cria novo
        with open(TEMP_CSV, 'w', encoding='utf-8', newline='') as wf:
            writer = csv.DictWriter(wf, fieldnames=fieldnames, delimiter=';')
            writer.writeheader()
            writer.writerow({'url': link, 'conteudo': conteudo, 'resumo': resumo})

    # Substitui o original pelo atualizado
    os.replace(TEMP_CSV, CSV_PATH)

def ler_resumo(link):
    with open(CSV_PATH, encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f, delimiter=';'):
            if row['url'] == link:
                return row.get('resumo', "")
    return ""

# ——— 5) Interface Streamlit ———
st.title("📝 Analisador de Atas do COPOM com IA")
st.write("Clique abaixo para buscar a última ata, visualizar e resumir automaticamente.")

if st.button("📥 Buscar e Analisar Última Ata"):
    with st.spinner("🔍 Buscando a última ata..."):
        link, driver = pegar_nova_ata()
        conteudo = pegar_conteudo_nova_ata(link, driver)

        # Cria CSV se não existir
        if not os.path.exists(CSV_PATH):
            with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(['url', 'conteudo', 'resumo'])

        # Gera ou carrega resumo
        if resumo_ja_existe(link):
            resumo = ler_resumo(link)
        else:
            resumo = gerar_resumo(conteudo)
            atualizar_csv_com_resumo(link, conteudo, resumo)

    # Extrai data da URL e formata
    try:
        data_str = link.rstrip('/').split('/')[-1]
        data_formatada = datetime.strptime(data_str, "%d%m%Y").strftime("%d/%m/%Y")
    except Exception:
        data_formatada = "Data não reconhecida"

    st.success("✅ Análise concluída!")
    st.markdown(f"**URL da ata:** {link}")

    with st.expander("Ver Texto Completo da Ata"):
        st.text_area("Conteúdo da Ata", conteudo, height=300)

    st.subheader(f"📄 Resumo da ATA de {data_formatada}")
    st.markdown(resumo)

st.sidebar.title("Sobre")
st.sidebar.info(
    "Desenvolvido em Streamlit + Selenium + Gemini\n\n"
    "- Busca automática da última ata do COPOM\n"
    "- Geração de resumo em bullet points\n"
    "- Histórico salvo em CSV\n"
)