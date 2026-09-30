<script lang="ts">
  import { resolve } from "$app/paths";
  import PageFrame from "$lib/components/PageFrame.svelte";
  import { date, integer, percentWhole } from "$lib/format";
  import { ruleLabel } from "$lib/issues";

  const { data } = $props();

  const REPOSITORY = "https://github.com/viniaraujo68/fund-monitor/blob/main/docs";

  const SECTIONS = [
    { id: "problema", title: "O problema" },
    { id: "universo", title: "Fontes e universo" },
    { id: "fluxo", title: "O fluxo" },
    { id: "calculos", title: "Os cálculos" },
    { id: "qualidade", title: "A qualidade" },
    { id: "achados", title: "Três achados" },
    { id: "limitacoes", title: "Limitações" },
    { id: "producao", title: "Em produção" },
  ];

  const QUESTIONS = [
    "Como cada fundo rendeu, contra o próprio benchmark e contra os pares?",
    "Para onde o dinheiro está indo?",
    "Em que dado não dá para confiar?",
  ];

  const SOURCES = [
    { name: "CVM, cadastro", use: "Quem é da gestora, classificação, público, benchmark declarado" },
    { name: "CVM, informe diário", use: "Cota, PL, captação, resgate e cotistas de todos os fundos do país" },
    { name: "Bacen, CDI", use: "Benchmark e taxa livre de risco" },
    { name: "ANBIMA, IMA-B, IMA-B 5, IMA-B 5+ e IRF-M", use: "Benchmark da renda fixa que não é DI" },
    { name: "B3, Ibovespa e IBrX-100", use: "Benchmark das ações" },
  ];

  const STEPS = [
    { label: "Entrada", name: "Fontes", detail: "CVM cadastro e informe · Bacen CDI · ANBIMA IMA-B, IMA-B 5, IMA-B 5+ e IRF-M · B3 Ibovespa e IBrX-100" },
    { label: "Etapa 1", name: "Coleta", detail: "Baixa as cinco fontes e confere cada resposta antes de gravar" },
    { label: "Etapa 2", name: "Cálculo", detail: "Retorno, risco, captação e pares, por série de cota" },
    { label: "Etapa 3", name: "Qualidade", detail: "Nove regras marcam o dado suspeito, sem apagar nada" },
    { label: "Etapa 4", name: "Publicação", detail: "Arquivos estáticos que este site lê" },
  ];

  const FORMULAS = [
    { name: "Retorno", formula: "cota no fim ÷ cota no início − 1", note: "A cota já é líquida de taxa. Anualizado só a partir de 12 meses, em 252 dias úteis." },
    { name: "% do CDI", formula: "retorno do fundo ÷ retorno do CDI", note: "Em todas as janelas, quando o CDI do período é positivo." },
    { name: "Volatilidade", formula: "desvio-padrão dos retornos diários × √252", note: "Quanto o fundo oscila num ano. Pede pelo menos 60 dias." },
    { name: "Drawdown", formula: "cota ÷ maior cota até ali − 1", note: "A maior queda desde um pico, com as datas do pico, do vale e da volta." },
    { name: "Sharpe", formula: "(retorno − CDI) ÷ volatilidade, anualizados", note: "CDI como taxa livre de risco. Some no fundo DI: com oscilação perto de zero, a razão vira ruído." },
    { name: "Benchmark próprio", formula: "o índice que o fundo declara no cadastro", note: "Quando o monitor coleta esse índice: IMA-B, IMA-B 5, IMA-B 5+, IRF-M ou IBrX-100. Se não, CDI para DI e multimercado, IMA-B para renda fixa, Ibovespa para ações." },
    { name: "Pares", formula: "(pares abaixo + ½ empates) ÷ pares", note: "Mesma classificação ANBIMA, público geral, PL acima de R$ 50 mi. Retorno e volatilidade lado a lado: rendeu mais que X % oscilando mais que Y %." },
    { name: "Decomposição do PL", formula: "PL fim − PL início − captação − PL início × retorno", note: "O que sobra aponta dado errado ou evento que o informe não descreve." },
  ];

  const OUTCOMES = [
    { name: "Aberto", detail: "Ainda sem leitura: é o que precisa ser investigado." },
    { name: "Explicado", detail: "O dado está certo e o movimento tem motivo." },
    { name: "Erro da fonte", detail: "A CVM publicou errado." },
    { name: "Limitação", detail: "O dado é o que a fonte dá, mas não representa o fato." },
  ];

  const FINDINGS = [
    {
      when: "09/12/2024",
      title: "Evento de crédito",
      text: "10 fundos de crédito da casa (13 séries) caíram no mesmo dia, de −0,11 % a −0,53 %, sem que o Ibovespa ou o IMA-B explicassem. Fundos de crédito de outras gestoras também caíram, como o JGP (−1,50 %) e o Premium Institucional (−2,07 %): provável remarcação de um emissor presente em várias carteiras.",
    },
    {
      when: "16/03/2026",
      title: "Linha zerada",
      text: "Um fundo com R$ 119 mi e 1.470 cotistas apareceu com cota, PL e cotistas zerados. Erro de envio: a linha sai do cálculo e fica marcada.",
    },
    {
      when: "Todo mês",
      title: "Distribuição informada como resgate",
      text: "O Incentivado em Infraestrutura (54023112000197) informa resgate de cerca de 1 % do PL por mês, mas o PL não cai isso. Provável pagamento de rendimentos que sai da cota.",
    },
  ];

  const LIMITATIONS = [
    "Cota sem ajuste por evento: quem paga rendimentos, como os incentivados, parece render menos do que rendeu.",
    "Tudo antes do IR do cotista, o que tira a vantagem do fundo isento.",
    "Quem declara “OUTROS” no cadastro segue a classificação. A Inflação Curta e o Igaraté Long Biased IMA B-5 são comparados com o IMA-B e com o Ibovespa, mas pelo nome são de IMA-B 5, e contra ele os dois perdem.",
    "Pares com viés de sobrevivência: exigir 12 meses, PL acima de R$ 50 mi e cota em dia hoje deixa de fora quem fechou ou encolheu.",
    "FIC e master da mesma estratégia contam como dois pares.",
    "PL e captação da gestora somam o FIC da casa e o fundo em que ele investe: parte do dinheiro conta duas vezes. Caso certo: o Incentivado em Infraestrutura e o FIC dele, com o mesmo PL. Separar pede a carteira de cada FIC.",
    "Sem carteira: o evento de crédito é inferido pela cota, não pelos ativos.",
    "Dado público chega com 2 a 3 dias úteis de atraso.",
  ];

  const PRODUCTION = [
    { name: "Fonte certa", detail: "Cota da casa pelo administrador no D0 ou D+1, pronta antes da abertura. A CVM fica para os pares e para conferir o que foi enviado." },
    { name: "Um fluxo por fonte", detail: "Orquestrador com uma tarefa por fonte: se a CVM cai, só o que depende dela espera." },
    { name: "Bruto guardado", detail: "Cada versão do arquivo da fonte, para refazer qualquer dia do passado." },
    { name: "Alerta com dono", detail: "Tratativa com dono e prazo, relatório diário só com o que é novo, alta bloqueando só a série afetada." },
    { name: "Precisão medida", detail: "Por regra, quantos alertas eram fato e quantos eram ruído: é o que calibra os limiares." },
  ];

  const DOCUMENTS = [
    { file: "DECISIONS.md", label: "Decisões e metodologia completas" },
    { file: "findings.md", label: "Achados nos dados reais" },
    { file: "PRODUCTION.md", label: "Como seria em produção" },
  ];

  const universe = $derived(data.meta.universe);
</script>

<PageFrame
  title="Como funciona"
  description={`O monitor em oito passos. Dados até ${date(data.meta.as_of)}.`}
  wide
>
  <nav aria-label="Seções" class="flex flex-wrap gap-2">
    {#each SECTIONS as section, index (section.id)}
      <a class="btn btn-sm btn-ghost border-base-content/10 border" href={`#${section.id}`}>
        <span class="text-base-content/60 tabular-nums">{index + 1}</span>
        {section.title}
      </a>
    {/each}
  </nav>

  <section id="problema" class="slide" aria-labelledby="problema-title">
    <p class="step">1</p>
    <h2 id="problema-title">O problema</h2>
    <p class="lead">
      Acompanhar todo dia os fundos da Icatu Vanguarda só com dado público, e saber quando o
      dado não merece confiança.
    </p>
    <ol class="grid gap-3 sm:grid-cols-3">
      {#each QUESTIONS as question, index (question)}
        <li class="box">
          <span class="text-primary text-2xl font-semibold tabular-nums">{index + 1}</span>
          <span>{question}</span>
        </li>
      {/each}
    </ol>
  </section>

  <section id="universo" class="slide" aria-labelledby="universo-title">
    <p class="step">2</p>
    <h2 id="universo-title">Fontes e universo</h2>
    <div class="grid gap-6 lg:grid-cols-2">
      <ul class="flex flex-col gap-2">
        {#each SOURCES as source (source.name)}
          <li class="box-row">
            <span class="font-medium">{source.name}</span>
            <span class="text-base-content/70 text-sm">{source.use}</span>
          </li>
        {/each}
      </ul>
      <div class="flex flex-col gap-3">
        <div class="grid grid-cols-2 gap-3">
          <div class="box">
            <span class="stat-number">{integer(universe.monitored_series)}</span>
            <span class="text-sm">séries não exclusivas</span>
          </div>
          <div class="box">
            <span class="stat-number">{integer(universe.general_public_series)}</span>
            <span class="text-sm">de Público Geral, em destaque</span>
          </div>
        </div>
        <p>
          <strong>Sem exclusivos.</strong> São
          {data.exclusiveShare === null ? "a maior parte" : percentWhole(data.exclusiveShare)} do PL da
          gestora, cada um com um cotista só: a captação é decisão do cliente, e não há par para comparar.
        </p>
        <p>
          <strong>Público Geral em destaque.</strong> É o produto de prateleira, o que qualquer investidor
          compara. Os pares são {integer(universe.peer_eligible)} fundos do país inteiro.
        </p>
      </div>
    </div>
  </section>

  <section id="fluxo" class="slide" aria-labelledby="fluxo-title">
    <p class="step">3</p>
    <h2 id="fluxo-title">O fluxo</h2>
    <ol class="flow">
      {#each STEPS as step, index (step.name)}
        <li class="flow-step">
          <span class="text-base-content/60 text-xs tabular-nums">{step.label}</span>
          <span class="text-lg font-semibold">{step.name}</span>
          <span class="text-base-content/70 text-sm">{step.detail}</span>
        </li>
        {#if index < STEPS.length - 1}
          <li class="flow-arrow" aria-hidden="true">
            <svg viewBox="0 0 24 24" class="size-6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M5 12h14" />
              <path d="m13 6 6 6-6 6" />
            </svg>
          </li>
        {/if}
      {/each}
    </ol>
    <p>
      Uma rotina roda sozinha de segunda a sexta às 20h17, refaz tudo e publica este site. O código e os
      dados de cada dia ficam no repositório, então qualquer dia pode ser refeito.
    </p>
  </section>

  <section id="calculos" class="slide" aria-labelledby="calculos-title">
    <p class="step">4</p>
    <h2 id="calculos-title">Os cálculos</h2>
    <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {#each FORMULAS as item (item.name)}
        <article class="box">
          <h3 class="font-semibold">{item.name}</h3>
          <p class="formula">{item.formula}</p>
          <p class="text-base-content/70 text-sm">{item.note}</p>
        </article>
      {/each}
    </div>
    <p>
      Contra o próprio benchmark, <strong>{data.benchmark.beat} de {data.benchmark.ranked}</strong>
      fundos de Público Geral com 12 meses bateram o índice nos últimos 12 meses.
    </p>
  </section>

  <section id="qualidade" class="slide" aria-labelledby="qualidade-title">
    <p class="step">5</p>
    <h2 id="qualidade-title">A qualidade</h2>
    <p class="lead">
      Nove regras marcam o dado suspeito. Marcar não apaga: o número continua no cálculo, com o aviso.
    </p>
    <div class="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
      <div class="flex flex-col gap-3">
        <ul class="grid gap-2 sm:grid-cols-2">
          {#each OUTCOMES as outcome (outcome.name)}
            <li class="box">
              <span class="font-medium">{outcome.name}</span>
              <span class="text-base-content/70 text-sm">{outcome.detail}</span>
            </li>
          {/each}
        </ul>
        <p>
          <strong>Dia de mercado.</strong> Um salto de cota não é suspeito se o índice mais parecido com o
          fundo também saiu do padrão, no mesmo sentido. Aí ele vira informativo.
        </p>
        <p>
          Hoje há <strong>{integer(data.openTotal)}</strong>
          {data.openTotal === 1 ? "alerta aberto" : "alertas abertos"}, a investigar.
          <a class="link" href={resolve("/qualidade")}>Ver a lista</a>.
        </p>
      </div>
      <div class="min-w-0">
        <p class="mb-2 text-sm font-medium">
          O que cada regra encontrou: é assim que se sabe se o limiar está certo
        </p>
        <div class="overflow-x-auto">
          <table class="table-sm table tabular-nums">
            <thead>
              <tr>
                <th>Regra</th>
                <th class="text-right">Abertos</th>
                <th class="text-right">Explicados</th>
                <th class="text-right">Erro da fonte</th>
                <th class="text-right">Limitação</th>
                <th class="text-right">Informativos</th>
              </tr>
            </thead>
            <tbody>
              {#each data.outcomes as outcome (outcome.rule)}
                <tr class={outcome.total === 0 ? "text-base-content/50" : ""}>
                  <td class="whitespace-nowrap">{ruleLabel(outcome.rule)}</td>
                  <td class="text-right">{integer(outcome.open)}</td>
                  <td class="text-right">{integer(outcome.explained)}</td>
                  <td class="text-right">{integer(outcome.sourceError)}</td>
                  <td class="text-right">{integer(outcome.limitation)}</td>
                  <td class="text-right">{integer(outcome.info)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </section>

  <section id="achados" class="slide" aria-labelledby="achados-title">
    <p class="step">6</p>
    <h2 id="achados-title">Três achados</h2>
    <div class="grid gap-3 lg:grid-cols-3">
      {#each FINDINGS as finding (finding.title)}
        <article class="box">
          <span class="text-base-content/60 text-xs">{finding.when}</span>
          <h3 class="font-semibold">{finding.title}</h3>
          <p class="text-sm">{finding.text}</p>
        </article>
      {/each}
    </div>
  </section>

  <section id="limitacoes" class="slide" aria-labelledby="limitacoes-title">
    <p class="step">7</p>
    <h2 id="limitacoes-title">Limitações que importam</h2>
    <ul class="grid gap-2 lg:grid-cols-2">
      {#each LIMITATIONS as limitation (limitation)}
        <li class="box-row">{limitation}</li>
      {/each}
    </ul>
  </section>

  <section id="producao" class="slide" aria-labelledby="producao-title">
    <p class="step">8</p>
    <h2 id="producao-title">Como seria em produção</h2>
    <p class="lead">
      Aqui a gestora é vista de fora, pelo que envia à CVM. Dentro dela, a ordem das fontes se inverte.
    </p>
    <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
      {#each PRODUCTION as item (item.name)}
        <article class="box">
          <h3 class="font-semibold">{item.name}</h3>
          <p class="text-base-content/70 text-sm">{item.detail}</p>
        </article>
      {/each}
    </div>
  </section>

  <section class="flex flex-col gap-2" aria-labelledby="documentos-title">
    <h2 id="documentos-title" class="text-base font-semibold">Para ler com calma</h2>
    <ul class="flex flex-wrap gap-2">
      {#each DOCUMENTS as document (document.file)}
        <li>
          <a class="btn btn-sm btn-outline" href={`${REPOSITORY}/${document.file}`} target="_blank" rel="noreferrer">
            {document.label}
          </a>
        </li>
      {/each}
    </ul>
  </section>
</PageFrame>

<style>
  .slide {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    scroll-margin-top: 1rem;
    padding: 1.25rem;
    border: 1px solid color-mix(in oklab, var(--color-base-content) 10%, transparent);
    border-radius: var(--radius-box);
    background: var(--color-base-100);
  }

  @media (min-width: 40rem) {
    .slide {
      padding: 1.75rem;
    }
  }

  .slide h2 {
    font-size: 1.375rem;
    font-weight: 600;
    letter-spacing: -0.01em;
  }

  .step {
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--color-primary);
    margin-bottom: -0.75rem;
  }

  .lead {
    font-size: 1.0625rem;
    max-width: 60rem;
  }

  .box {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
    min-width: 0;
    padding: 0.875rem 1rem;
    border-radius: var(--radius-field);
    background: var(--color-base-200);
  }

  .box-row {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
    padding: 0.625rem 0.875rem;
    border-radius: var(--radius-field);
    background: var(--color-base-200);
  }

  .stat-number {
    font-size: 1.875rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    line-height: 1.1;
  }

  .formula {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.8125rem;
    overflow-wrap: anywhere;
  }

  .flow {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 0.5rem;
  }

  .flow-step {
    display: flex;
    flex: 1 1 0;
    flex-direction: column;
    gap: 0.25rem;
    min-width: 0;
    padding: 1rem;
    border: 1px solid color-mix(in oklab, var(--color-primary) 35%, transparent);
    border-radius: var(--radius-field);
    background: color-mix(in oklab, var(--color-primary) 6%, var(--color-base-100));
  }

  .flow-arrow {
    display: flex;
    justify-content: center;
    color: var(--color-primary);
    transform: rotate(90deg);
  }

  @media (min-width: 64rem) {
    .flow {
      flex-direction: row;
      align-items: center;
    }

    .flow-step {
      align-self: stretch;
    }

    .flow-arrow {
      transform: none;
    }
  }
</style>
