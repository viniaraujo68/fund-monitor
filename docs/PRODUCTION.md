# Como seria em produção

Este protótipo roda num processo só, uma vez por dia, e publica JSON estático. Funciona para 75 séries de uma gestora e um leitor. Uma mesa que decide com esses números precisa de mais: saber quando um dado chegou atrasado, reproduzir o que viu num dia passado e não publicar um número errado. Abaixo, o que eu mudaria, em que ordem, e o que conseguiria fazer sozinho.

## 1. Ponto de partida

O caminho é contínuo, não uma reescrita. O protótipo já tem as peças que um sistema de produção reaproveita:

- **Coletor idempotente.** O informe diário só é baixado de novo quando o tamanho ou o Last-Modified mudam. Cada dia da ANBIMA é gravado uma vez e não é pedido de novo. Rodar duas vezes dá o mesmo resultado.
- **Bruto reproduzível.** O bruto fica fora do git e pode ser refeito pelo pipeline. O Parquet normalizado e o JSON do site ficam versionados.
- **Rotina diária.** Uma GitHub Action roda de segunda a sexta, às 20h de Brasília: testes, pipeline, build do site, e commit de `data/` quando há mudança. Cada commit é uma foto do que foi publicado.
- **Contrato do JSON.** Os modelos pydantic de `publish/site_json.py` recusam campo a mais ou a menos. O front depende desse contrato, não do formato do Parquet.
- **Regras como código testado.** As 9 regras de qualidade estão em `quality/checks.py`, com limiares em constantes com nome e testes em `pipeline/tests/`.

## 2. Orquestração

- **Um fluxo por fonte**, em Dagster ou Airflow: cadastro CVM, informe diário, Bacen, ANBIMA e B3. Hoje, se a CVM cai, tudo espera; foi o que aconteceu em 26 e 27/09/2026. Separado, só o que depende da CVM espera, e o resto publica com o alerta de fonte atrasada.
- **Partição por `(fonte, data)`.** Backfill é reprocessar partições. Como a coleta já é idempotente, reprocessar não duplica nada.
- **Dependências explícitas.** O cálculo só roda quando o dia do informe está completo. A regra dos 90 % das séries vira um sensor, em vez de um filtro dentro do cálculo.
- **Retry com espera crescente** nas fontes instáveis (portal da CVM, formulário da ANBIMA). Depois do último retry, alerta.
- **Por que Dagster:** o modelo de "ativos" (arquivo bruto → Parquet → métricas → JSON) é o desenho que o pipeline já tem. Airflow também serve; a escolha depende do que a casa já usa.

## 3. Armazenamento

| Camada | Hoje | Em produção |
| --- | --- | --- |
| Bruto | `data/raw/`, sobrescrito quando a CVM republica | S3 imutável, particionado por fonte e data, **guardando cada versão** do arquivo |
| Normalizado | Parquet no git | Parquet no lake, particionado por fonte e mês |
| Analítico | Parquet de métricas | Postgres, ou DuckDB/Athena sobre o lake |
| Entrega | JSON estático por fundo | API com cache, lida pelo site e por outras ferramentas da mesa |

Guardar cada versão do bruto importa porque a CVM regrava o histórico. Em 27/09/2026 ela regravou 25 meses. Hoje o arquivo antigo é substituído e a diferença só aparece se alguém comparar na hora.

## 4. Qualidade

- **As 9 regras como testes de dados** dentro do fluxo, com as mesmas funções de hoje ou com Great Expectations.
- **Severidade alta bloqueia a publicação da série afetada**, não do site inteiro. Uma linha zerada num fundo não deveria segurar os outros 74.
- **Relatório diário para a mesa com o que é novo.** Hoje a lista acumula 24 meses: são 148 alertas, e o alerta de ontem se perde entre eles.
- **Estado do alerta.** Visto, explicado, erro da fonte. Hoje o alerta não tem dono nem status, e o mesmo caso aparece todo dia.
- **Limiares revisados com a mesa.** 5 desvios-padrão, 0,1 %, 1 % do PL e 10 % do mercado foram calibrados olhando 24 meses de uma gestora. Precisam de uma revisão com quem usa o alerta.

## 5. Observabilidade

- **Log estruturado** em JSON por etapa: linhas lidas, séries, alertas, duração. Hoje o log já traz essas contagens, mas em texto.
- **Frescor por fonte como métrica.** A regra 8 já calcula o atraso de cada fonte; em produção esse número vai para um painel, não só para o JSON.
- **Painel de saúde:** última execução, duração, fontes atrasadas, alertas novos por severidade.
- **Alerta no canal da mesa** quando a execução falha ou uma fonte passa da tolerância. Hoje só existe o aviso padrão do GitHub quando a Action falha.

## 6. Governança

- **Dicionário de dados.** Cada campo publicado com unidade, fonte e coluna de origem. Exemplo: `pct_cdi_12m` é fração, razão de retornos acumulados, vazia com menos de 12 meses.
- **Versão das fórmulas.** Um número de versão do cálculo gravado junto de cada publicação. Quando um limiar muda, dá para saber qual versão gerou cada número.
- **Reprodutibilidade por data de referência.** Com o bruto imutável e o código versionado, dá para recalcular exatamente o que a mesa viu em qualquer dia. Hoje o histórico do git dá a foto do JSON, mas não garante o recálculo, porque o bruto antigo não é guardado.
- **Cadastro por data.** Guardar a foto diária do cadastro, para que uma mudança de classificação não reescreva o passado.

## 7. Extensões

Em ordem de valor para a mesa, como eu vejo:

1. **Decomposição diária do PL.** Resolve o resíduo inflado de fundos com fluxo grande no mês, como `54198519000155-TY3I61766775472` em fev/2026. É a menor das mudanças e usa só o dado que já existe.
2. **Cota ajustada por evento.** Precisa de uma fonte de amortizações e distribuições, que o informe não tem. Corrige o retorno e a posição entre pares dos incentivados.
3. **Carteiras (CDA da CVM)** para exposição por emissor e por setor. Teria dito qual emissor explica o 09/12/2024. A CDA é mensal: serve para exposição, não para o dia a dia.
4. **Benchmark ANBIMA completo com contrato**, com o índice do regulamento de cada fundo (IMA-B 5, IRF-M, IMA-S), no lugar da regra por classificação e do download dia a dia.
5. **Comparação entre gestoras.** O cadastro e o informe já cobrem o país, e os pares já leem 3.392 séries. Trocar o CNPJ da gestora por uma lista é pouco código; o custo é de leitura e armazenamento.
6. **Pares para Qualificado e Profissional**, com o mesmo método.
7. **Marcação a mercado das posições com curva de juros.** É o passo seguinte natural, e foi deixado de fora de propósito neste case. Não está construído.

## 8. Custo e equipe

Os dados são públicos e de graça. O custo está no tempo das pessoas e, se a ANBIMA for por contrato, na licença.

| Eu faria sozinho | Pediria à engenharia |
| --- | --- |
| Regras e fórmulas novas, com teste | Conta, permissões e buckets no S3 |
| Decomposição diária do PL e coletor da CDA | Orquestrador em produção, com deploy e segredos |
| Dicionário de dados e versão das fórmulas | API com cache e autenticação |
| Relatório diário de alertas novos | Painel de observabilidade e alerta no canal |
| Fluxos no Dagster rodando localmente | Plantão e acordo de nível de serviço |
| Calibrar limiares com a mesa | Contrato com a ANBIMA (com compras e jurídico) |

A divisão é: o que é regra de negócio e dado fica comigo; o que é infraestrutura compartilhada, segurança e plantão fica com quem mantém a infraestrutura da casa.
