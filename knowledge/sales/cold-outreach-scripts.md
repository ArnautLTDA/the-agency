# Playbook Canônico de Abordagem Comercial e Ganchos de Abertura (Cold Outreach)

> **Versão:** 2.0 (Refinada com padrões `agency-agents` e `SalesGPT`)  
> **Finalidade:** Biblioteca oficial de ganchos de abertura para prospecção ativa no WhatsApp.  
> **Autoridade:** Aprovado por João — *"A Palavra do Chefe é Sempre Lei"*.

---

## 1. Diretrizes Pétreas de Abordagem

1. **Teto Estrito de Extensão:**
   - Toda mensagem de abertura possui **teto rígido de 25 a 30 palavras**. No WhatsApp brasileiro, mensagens com mais de 35 palavras parecem panfleto, mala-direta ou golpe e são sumariamente ignoradas.
2. **Personalização Tripla Mandatória:**
   - Toda mensagem DEVE conter 3 variáveis dinâmicas extraídas da ficha minerada:
     - `{{business_name}}`: Nome fantasia real do estabelecimento.
     - `{{neighborhood}}`: Bairro ou região onde o estabelecimento está localizado.
     - `{{review_highlight}}`: Elogio factual a um ponto forte citado por clientes reais no Google Maps.
3. **Pergunta Final Única:**
   - A mensagem DEVE terminar obrigatoriamente com UMA única pergunta curta, aberta e sem fricção. Proibido fazer múltiplas perguntas ou empurrar reuniões de 30 minutos na abertura.
4. **Zero Menção a Robô ou IA:**
   - O vendedor se posiciona como consultor de sistemas/tecnologia da The Agency conversando diretamente com o proprietário.

---

## 2. Regras Operacionais e Cadência Anti-Ban

* **Janela Comercial:** Disparos autorizados exclusivamente de **Segunda a Sexta-feira, das 08:30 às 18:30 (horário de Brasília)**. Mensagens enviadas à noite ou fins de semana geram denúncia de spam imediata.
* **Teto por SIM Card / Linha:** Máximo de **25 a 30 novos contatos por dia** por número de WhatsApp.
* **Intervalo / Jitter Natural:** Atraso randômico entre **15 e 45 segundos** entre conversas diferentes.
* **Simulação de Digitação (`is_composing`):** Antes de enviar a mensagem, o gateway mantém o status "digitando..." por **3 a 7 segundos** proporcionais ao tamanho do texto.

---

## 3. Scripts de Abertura por Nicho de Mercado

### 3.1 Nicho: Barbearias & Salões Masculinos
* **Contexto:** Dono ou barbeiro principal atendendo clientes no balcão e cortando cabelo; sem tempo para digitar.
* **Gancho A (Foco em Agendamento & Fila):**
  > "Opa, tudo bem? Vi os elogios da {{business_name}} aqui no {{neighborhood}}, principalmente sobre {{review_highlight}}. Vocês ainda usam caderno ou WhatsApp pra agendar horário?"
  *(25 palavras)*
* **Gancho B (Foco em Experiência do Cliente):**
  > "E aí, tudo bom? Achei excelente o trabalho da {{business_name}} no {{neighborhood}}. Notei que elogiam muito {{review_highlight}}. Como vocês organizam os horários no sábado?"
  *(26 palavras)*

### 3.2 Nicho: Oficinas Mecânicas & Auto Centers
* **Contexto:** Dono com a mão graxenta, barulho alto na oficina, lê mensagens rápidas.
* **Gancho A (Foco em Orçamento e Confiança):**
  > "Olá, tudo bem? Vi as avaliações da {{business_name}} no {{neighborhood}}, parabéns pela nota e por {{review_highlight}}. Vocês costumam passar orçamento de peças pelo WhatsApp?"
  *(26 palavras)*
* **Gancho B (Foco em Pós-Venda e Retenção):**
  > "Tudo bem por aí? Parabéns pelo serviço da {{business_name}} aqui no {{neighborhood}}, vi que destacam {{review_highlight}}. Como o cliente acompanha o status do carro hoje?"
  *(26 palavras)*

### 3.3 Nicho: Clínicas de Estética & Harmonização
* **Contexto:** Mercado visual, alta preocupação com estética e pontualidade.
* **Gancho A (Foco em Cardápio de Procedimentos):**
  > "Olá, tudo bem? Encantada com o espaço da {{business_name}} no {{neighborhood}}, vi muitos elogios sobre {{review_highlight}}. Vocês têm cardápio digital dos procedimentos para enviar às pacientes?"
  *(28 palavras)*
* **Gancho B (Foco em Sinal e Redução de No-Show):**
  > "Oi, tudo bem? Parabéns pela reputação da {{business_name}} no {{neighborhood}}, destacaram muito {{review_highlight}}. Vocês costumam cobrar sinal para reservar o horário dos procedimentos?"
  *(26 palavras)*

### 3.4 Nicho: Consultórios Odontológicos
* **Contexto:** Secretária ou dentista atendendo; buscam passar imagem de alta tecnologia e organização.
* **Gancho A (Foco em Confirmação e Pontualidade):**
  > "Olá, doutor(a), tudo bem? Vi a reputação impecável da {{business_name}} no {{neighborhood}}, parabéns pelo atendimento em {{review_highlight}}. Como vocês gerenciam as confirmações de consulta hoje?"
  *(27 palavras)*
* **Gancho B (Foco em Avaliação Inicial):**
  > "Olá, tudo bem? Estava vendo as ótimas avaliações da {{business_name}} no {{neighborhood}}, especialmente sobre {{review_highlight}}. O paciente consegue agendar a primeira consulta direto pelo celular?"
  *(27 palavras)*

### 3.5 Nicho: Pet Shops & Clínicas Veterinárias
* **Contexto:** Rotina caótica de banho e tosa, animais latindo, mensagens acumuladas no WhatsApp.
* **Gancho A (Foco em Agendamento de Banho e Tosa):**
  > "Oi, tudo bem? Vi o carinho que os tutores elogiam na {{business_name}} no {{neighborhood}}, principalmente {{review_highlight}}. Vocês ainda confirmam horários de banho e tosa manualmente?"
  *(26 palavras)*
* **Gancho B (Foco em Vacinas e Retorno):**
  > "Olá! Parabéns pelo trabalho na {{business_name}} no {{neighborhood}}, vi notas excelentes sobre {{review_highlight}}. Vocês avisam os clientes sobre o reforço das vacinas pelo WhatsApp?"
  *(26 palavras)*

### 3.6 Nicho: Restaurantes, Hamburguerias & Cafeterias
* **Contexto:** Dono focado na cozinha e salão; odeia pagar 27% de taxas abusivas de aplicativos de entrega.
* **Gancho A (Foco em Cardápio Próprio Sem Taxas):**
  > "Olá, tudo bem? Vi as fotos e elogios aos pratos da {{business_name}} no {{neighborhood}}, principalmente {{review_highlight}}. Vocês já têm cardápio digital próprio pra receber pedidos sem taxa?"
  *(28 palavras)*
* **Gancho B (Foco em Cardápio Interativo WhatsApp):**
  > "Oi, tudo certo? Parabéns pelo sucesso da {{business_name}} no {{neighborhood}}, vi vários comentários sobre {{review_highlight}}. Como o cliente faz para ver o cardápio e pedir pelo WhatsApp?"
  *(28 palavras)*

---

## 4. Cadência do Segundo Contato (Entrega da Isca Bespoke)

Assim que o lead responde à pergunta de abertura (mesmo que com um simples "sim", "uso caderno", ou "tudo bem, quem é?"), o Sales Executive avança imediatamente para a **Fase 2 (`DEMO_DELIVERY`)**:

> "Legal, [Nome]! Vi que muitos clientes elogiam vocês mas se perdem no WhatsApp. Tomei a liberdade de montar um protótipo com a marca da {{business_name}} pra você ver: {{demo_url}}. Dá uma olhada no celular, o que achou?"
*(40 palavras — com print mobile em anexo)*
