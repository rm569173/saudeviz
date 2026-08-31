# Roteiro do vídeo pitch — SaúdeViz

**Duração máxima: 5 minutos** · Challenge FIAP × Oracle 2026 · 1TSCOA
Lucas Ventura Araujo Ribas Colen — RM 569173

> **Como usar:** o texto em citação é o que você fala. O texto em itálico é
> instrução de tela. Ensaie duas vezes antes de gravar — a diferença entre um
> pitch bom e um ruim quase sempre é ensaio, não conteúdo.

---

## 1. Abertura e contextualização — 30 segundos

*Tela: slide de abertura do PPT com o nome do projeto*

> "Uma secretaria de saúde precisa responder três perguntas: onde as
> internações estão crescendo, quais atendimentos mais pressionam o sistema, e
> onde a capacidade hospitalar já foi ultrapassada.
>
> Hoje, cada uma dessas perguntas vira um chamado para a equipe técnica. O
> gestor espera dias por uma resposta que o paciente não pode esperar.
>
> Eu sou Lucas Colen, da turma 1TSCOA, e o SaúdeViz responde às três em
> segundos — aceitando a pergunta em português."

⏱️ *Não passe daqui de 30s. Se estourar, corte a frase do meio.*

---

## 2. Objetivo do projeto — 30 segundos

*Tela: slide com os números*

> "Trabalhei com dados reais e públicos: 5 milhões e meio de internações do
> SUS ocorridas em 2024 na região Sudeste — Espírito Santo, Minas, Rio e São
> Paulo. Isso são 89 milhões de habitantes e 10 bilhões de reais pagos pelo
> SUS num ano.
>
> Três fontes, nos três formatos que o desafio pede: o SIH/SUS relacional, o
> cadastro do CNES em JSON via API, e a população municipal do IBGE em CSV."

---

## 3. Proposta de solução — 1 minuto

*Tela: diagrama da arquitetura*

> "O caminho do dado é este. A ingestão baixa os arquivos do DATASUS por FTP e
> converte o formato proprietário `.dbc` — isso roda localmente, porque exige
> uma biblioteca compilada.
>
> A partir daí, tudo acontece no Databricks: Bronze com o dado bruto em Delta,
> Prata com limpeza e tipagem, Ouro com o modelo dimensional. A camada Ouro é
> gravada direto no Oracle Database 19c da FIAP — são nove tabelas
> `T_SAUDE_*`, e é de lá que o painel consulta.
>
> E aqui está a parte que eu quero destacar."

*Pausa. Tela: trecho do `ddl_oracle.sql` com os COMMENT ON*

> "O Select AI da Oracle traduz perguntas em português para SQL usando os
> comentários do dicionário de dados. Mas o Select AI só existe no Autonomous
> Database — eu verifiquei por consulta ao `all_objects` que a instância da
> FIAP, uma 19c Enterprise, não tem o pacote `DBMS_CLOUD_AI`.
>
> Então eu implementei o mecanismo equivalente sobre exatamente os mesmos
> metadados. Os comentários das minhas tabelas estão escritos em linguagem de
> negócio de propósito: são eles que alimentam o tradutor. Migrar para o
> Autonomous não exige remodelar nada — só trocar o motor de tradução."

---

## 4. Demonstração — 2 minutos ⭐ *a parte mais importante*

*Tela: painel ao vivo. Não use vídeo gravado de tela parada — navegue de verdade.*

**4a. Visão geral — 20s**

> "Este é o painel. Cinco milhões e meio de internações, permanência média de
> 4,86 dias, taxa de transferência de 4,2%."

**4b. Capacidade — 30s**

*Clique em Capacidade hospitalar*

> "Aqui está o indicador central: ocupação de leito por município e mês. Repare
> que eu mostro dois números lado a lado — a média simples e a ponderada. A
> simples trata um município de três leitos igual a São Paulo, e por isso
> engana. A distância entre as barras é o tamanho da distorção.
>
> E eu sou explícito na tela: ocupação acima de 1 é alerta para investigar,
> não prova de colapso. Pode ser leito desatualizado no CNES ou município-polo
> atendendo a região inteira. A ferramenta reduz 1.668 municípios a uma lista
> de dezenas — a decisão continua humana."

**4c. Perfis — 25s**

*Clique em Perfis de atendimento*

> "Esta tela responde 'quais atendimentos pressionam mais'. E a resposta não é
> a óbvia: eu não ordeno por volume, ordeno por leito ocupado.
>
> Saúde mental aparece no topo. É uma fatia pequena das internações e uma
> fatia muito maior dos leitos-dia, porque a permanência é três vezes maior.
> Isso é invisível num painel que só conta atendimentos — e muda a decisão:
> abrir leito clínico não resolve pressão psiquiátrica."

**4d. Pergunte em português — 45s** ⭐ *o momento do pitch*

*Clique em Pergunte em português*

> "E aqui está a cereja do bolo do desafio."

*Clique no exemplo "Onde a capacidade hospitalar está sendo ultrapassada?"*

> "Eu pergunto em português. O sistema reconhece a intenção, extrai os filtros,
> **mostra o SQL que gerou** — e executa no Oracle.
>
> O SQL continua sendo gerado e executado de verdade. O que o tradutor faz é
> tirar a barreira da sintaxe para quem toma a decisão."

*Digite uma pergunta diferente das dos exemplos, ao vivo — mostra que não é truque*

> "E quando ele não entende, ele diz que não entendeu, em vez de inventar um
> número. Num painel de saúde pública, essa diferença importa."

⏱️ *Se o tempo apertar, corte o item 4a. Nunca corte o 4d.*

---

## 5. Benefícios e achados — 30 segundos

*Tela: slide com os três achados*

> "Três coisas que os dados me ensinaram e que eu não sabia quando comecei.
>
> Primeira: a competência do SIH não é a data da internação. É o mês de
> pagamento. Quarenta e dois por cento dos registros de um mês são de meses
> anteriores. Se eu não tivesse descoberto isso, meu painel responderia uma
> pergunta financeira prometendo uma assistencial.
>
> Segunda: existe uma coluna, a `COBRANCA`, que revela transferência de
> paciente. Ela transforma 'há muitas internações aqui' em 'pacientes estão
> saindo daqui porque não há como tratá-los aqui'.
>
> Terceira: eu testei um modelo de previsão com tendência e sazonalidade, e
> ele perdeu para um modelo simples de perfil semanal — o erro dele subia de
> 6% para 27% conforme o horizonte aumentava. A demanda hospitalar não tem
> tendência explorável: o sinal está no ciclo semanal e nos feriados. Um
> feriado reduz internações em 26%, com variação de três pontos entre os
> quatro estados."

---

## 6. Conclusão e próximos passos — 30 segundos

> "O SaúdeViz está no ar, com o código aberto no GitHub e a camada analítica
> no Oracle.
>
> Os próximos passos são três: cruzar com dados de clima, para testar se chuva
> aumenta acidentes e frio aumenta internações respiratórias; estender o
> recorte para o Brasil inteiro, já que o pipeline é parametrizado por UF; e
> migrar para o Autonomous Database para ativar o Select AI nativo — o script
> já está entregue.
>
> Dados que salvam vidas. Decisões que transformam o sistema de saúde.
> Obrigado."

---

## Checklist antes de gravar

- [ ] Painel aberto e **já carregado** numa aba — a primeira carga demora
- [ ] Testar a página "Pergunte em português" antes de gravar
- [ ] Fechar notificações, e-mail e qualquer coisa que possa aparecer na tela
- [ ] Áudio: fone com microfone é melhor que o microfone do notebook
- [ ] Gravar em 1080p
- [ ] **Cronometrar o ensaio.** Se passar de 5 min, corte o item 4a e encurte o 3

## Erros que custam nota

| Erro | Por quê |
|---|---|
| Ler o slide em voz alta | O avaliador já leu. Fale o que **não** está escrito |
| Demo em vídeo gravado de tela parada | Parece que não funciona. Navegue ao vivo |
| Prometer o que não entregou | A banca da Oracle vai perguntar. Assuma os limites |
| Passar de 5 minutos | Regra explícita do enunciado |
| Terminar sem chamada final | O último som deve ser a frase de impacto, não "é isso" |

## Depois de gravar

1. Subir no YouTube como **não listado** ou **público** (nunca privado)
2. Criar o arquivo `.TXT` com: link do vídeo, nome da equipe, RM e nome em
   ordem alfabética — exigência explícita das regras gerais
3. Colocar o link também dentro do PPT
