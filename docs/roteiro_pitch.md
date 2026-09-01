# Roteiro do vídeo pitch — SaúdeViz

**Duração máxima: 5 minutos** · Challenge FIAP × Oracle 2026 · 1TSCOA
Lucas Ventura Araujo Ribas Colen — RM 569173

> **Como usar:** o texto em citação é o que você fala, palavra por palavra. O
> texto em itálico é o que aparece na tela.
>
> Os tempos não são estimativa: foram calculados por contagem de palavras a
> 150 por minuto, ritmo de fala clara. Rode `py docs/mede_pitch.py` depois de
> qualquer edição no texto falado — ele recalcula e avisa se estourou.
>
> Versão sem formatação para teleprompter em `docs/teleprompter_video.txt`.

**Fala: 4min39s. Sobram 21s** para as pausas de navegação da demo.

---

## 1. Abertura — 25s

*Tela: slide 1 do PPT, a capa*

> "Uma secretaria de saúde precisa responder três perguntas: onde as
> internações crescem, quais atendimentos mais pressionam o sistema, e onde a
> capacidade hospitalar já foi ultrapassada.
>
> Hoje cada uma vira um chamado para a equipe técnica. O gestor espera dias por
> uma resposta que o paciente não pode esperar.
>
> Eu sou Lucas Colen, turma 1TSCOA. O SaúdeViz responde às três em segundos — e
> aceita a pergunta em português."

---

## 2. Os dados — 22s

*Tela: slide 3, os números da entrega*

> "Dados reais e públicos: cinco milhões e meio de internações do SUS ocorridas
> em 2024 no Sudeste. Oitenta e nove milhões de habitantes, dez bilhões de
> reais num ano.
>
> Três fontes nos três formatos que o desafio pede: SIH relacional, CNES em
> JSON via API, IBGE em CSV. E uma quarta, de clima, que eu mostro no fim."

---

## 3. Arquitetura e o Select AI — 45s

*Tela: slide 13, o diagrama da arquitetura*

> "O caminho do dado é este. A ingestão baixa o DATASUS por FTP e converte o
> formato proprietário ponto-dbc, que exige biblioteca compilada em C.
>
> Daí em diante é Databricks: Bronze em Delta, Prata com limpeza e tipagem,
> Ouro com o modelo dimensional — gravada direto no Oracle 19c da FIAP, onze
> tabelas T-SAÚDE. É de lá que o painel consulta."

*Pausa curta. Tela: slide 42, a consulta ao all_objects*

> "Agora o ponto principal. O Select AI traduz português para SQL usando os
> comentários do dicionário de dados, mas só existe no Autonomous. Verifiquei
> no all_objects: a instância da FIAP é 19c Enterprise, não tem o
> DBMS_CLOUD_AI.
>
> Implementei o equivalente sobre os mesmos metadados. Os comentários das
> minhas tabelas estão em linguagem de negócio de propósito — são eles que
> alimentam o tradutor."

---

## 4. Demonstração ao vivo — 1min51s ⭐

*Tela: o painel de verdade, em saudeviz.streamlit.app. Navegue ao vivo:
vídeo de tela parada parece que não funciona.*

### 4a. Visão geral — 10s

> "Este é o painel, conectado ao Oracle da FIAP agora. Cinco milhões e meio de
> internações, permanência média de 4,86 dias, transferência de 4,2%."

### 4b. Capacidade — 25s

*Clique em Capacidade hospitalar*

> "O indicador central: ocupação de leito por município e mês. Eu mostro dois
> números lado a lado, média simples e ponderada. A simples trata um município
> de três leitos igual a São Paulo, e por isso engana — a distância entre as
> barras é a distorção.
>
> E sou explícito na tela: ocupação acima de um é alerta para investigar, não
> prova de colapso."

### 4c. Perfis de atendimento — 19s

*Clique em Perfis de atendimento*

> "Quais atendimentos pressionam mais. A resposta não é a óbvia, porque eu não
> ordeno por volume: ordeno por leito ocupado.
>
> Saúde mental aparece no topo. Fatia pequena das internações, fatia grande dos
> leitos-dia, porque a permanência é o dobro. Abrir leito clínico não resolve
> pressão psiquiátrica."

### 4d. Dimensionamento de leitos — 27s ⭐

*Clique em Previsão de demanda, role até o fim, com Belo Horizonte selecionado*

> "E aqui o painel deixa de descrever e passa a decidir. Esta curva diz quantos
> leitos a capital precisa ter aberto em cada mês.
>
> Belo Horizonte tem 6.312 cadastrados. A demanda comum, o piso que não pode
> ser desmobilizado, é 5.107. O pico é em abril e exige 797 a mais. Sobram 408
> leitos de folga: seis por cento. É a margem que uma epidemia consome em
> dias."

### 4e. Pergunte em português — 30s ⭐

*Clique em Pergunte em português*

> "E agora a cereja do bolo do desafio."

*Clique no exemplo "Onde a capacidade hospitalar está sendo ultrapassada?"*

> "Eu pergunto em português. O sistema reconhece a intenção, mostra o SQL que
> gerou, e executa no Oracle. Dez linhas retornadas do banco.
>
> O SQL continua sendo gerado e executado de verdade. O tradutor só tira a
> barreira da sintaxe de quem decide."

*Agora digite uma pergunta que NÃO está nos exemplos — prova que não é truque.
Sugestão: "quais hospitais têm maior permanência média em Minas Gerais?"*

⏱️ *Se o tempo apertar, corte o 4a inteiro. Nunca corte o 4d nem o 4e.*

---

## 5. O que os dados ensinaram — 50s

*Tela: slide 46, os três achados*

> "Três coisas que eu não sabia quando comecei.
>
> Primeira: a competência do SIH não é a data da internação, é o mês de
> pagamento. Quarenta e dois por cento dos registros de um mês são de meses
> anteriores. Sem isso, meu painel responderia uma pergunta financeira
> prometendo uma assistencial.
>
> Segunda: testei um modelo com tendência e sazonalidade e ele perdeu para um
> perfil semanal simples — o erro subia de seis para vinte e sete por cento. A
> demanda hospitalar não tem tendência explorável."

*Tela: slide 35, o gradiente da chuva*

> "Terceira, com a quarta fonte. Testei se chuva aumenta acidentes: não
> aumenta, e sem gradiente por intensidade. Hipótese refutada — isso também é
> resultado.
>
> Já o frio se associa a mais internação respiratória, nove por cento. Mas
> inverno também é temporada de vírus: é associação, não causa."

---

## 6. Conclusão — 26s

*Tela: slide 49, o encerramento*

> "O SaúdeViz está no ar, código aberto no GitHub, camada analítica no Oracle
> da FIAP.
>
> Próximos passos: separar o efeito do frio do efeito da sazonalidade viral;
> estender ao Brasil inteiro, já que o pipeline é parametrizado por estado; e
> migrar para o Autonomous para ativar o Select AI nativo — o script já está
> entregue.
>
> Dados que salvam vidas. Decisões que transformam o sistema de saúde.
> Obrigado."

---

## Antes de gravar

- [ ] Abrir `saudeviz.streamlit.app` e **deixar carregar até o fim** — a
      primeira carga acorda o app e demora
- [ ] Confirmar que a barra lateral mostra **Conectado ao Oracle**, não
      "Modo contingência"
- [ ] Visitar a página "Pergunte em português" uma vez antes, para o cache
      estar quente
- [ ] Na página de previsão, já deixar **Belo Horizonte** selecionado
- [ ] Fechar e-mail, notificações e qualquer coisa que possa aparecer na tela
- [ ] Fone com microfone — o do notebook capta eco da sala
- [ ] Gravar em 1080p
- [ ] **Cronometrar um ensaio inteiro** antes da tomada boa

## Erros que custam nota

| Erro | Por quê |
|---|---|
| Ler o slide em voz alta | O avaliador já leu. Fale o que **não** está escrito |
| Demo em tela parada | Parece que não funciona. Navegue ao vivo |
| Prometer o que não entregou | A banca da Oracle pergunta. Assuma os limites |
| Passar de 5 minutos | Regra explícita do enunciado |
| Terminar sem frase final | O último som deve ser o impacto, não "é isso" |

## Depois de gravar

1. Subir no YouTube com visibilidade **Pública**. A regra 11 das regras
   gerais pede "privilégio de acesso público" — **não** use "não listado"
2. Preencher `link_video.txt` com a URL
3. Rodar `py docs/gera_ppt.py` para o link entrar no slide 45 do PPT
