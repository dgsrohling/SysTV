# SysTV – Painel de Licitações

Painel web simples, feito em Flask, que exibe os dados da planilha de acompanhamento de licitações de obras (Google Sheets).
Foi pensado para ficar aberto em uma TV ou no navegador: **a tela se atualiza sozinha** sempre que a planilha muda, sem precisar recarregar a página.

O sistema apenas **lê e exibe** a planilha. Nenhum dado é alterado ou gravado: para mudar algo no painel, edite a planilha.

---

## Exibições

| Endereço | O que mostra |
|---|---|
| `/` | **Painel completo:** indicadores (processos, valor orçado total, homologados, próxima abertura), cards dos processos, gráficos por fase, secretaria e responsável, e tabela detalhada com filtros e busca. |
| `/cards` | **Somente os cards** dos processos. |
| `/secretarias` | **Processos por secretaria:** uma coluna por secretaria, com a quantidade de processos, o valor orçado e os cards daquela secretaria. |

Cada card mostra a obra, a secretaria, a fase do certame, os valores orçado e vencedor (com desconto calculado), a data de abertura, o responsável, o presidente da comissão, a observação, o nº SEI e a data da última atualização. Os processos habilitados ou homologados recebem uma etiqueta.

### Modo TV

Acrescente `?tv=1` a qualquer endereço, por exemplo `http://<ip-do-servidor>:8050/secretarias?tv=1`.
Nesse modo as letras ficam maiores e a navegação, os filtros e a tabela ficam escondidos. Também há o link **"Modo TV"** no cabeçalho de cada exibição.

### Filtros pelo endereço

Os filtros funcionam em todas as exibições pelo próprio endereço. Assim, uma TV pode mostrar só uma parte dos processos:

```
/cards?secretaria=SEDUC
/secretarias?responsavel=VALDIR&tv=1
/?q=escola
```

Filtros disponíveis: `secretaria`, `responsavel`, `presidente`, `fase_nome` e `q` (busca livre). No painel `/`, eles também aparecem como campos na tela.

---

## Como funciona a atualização

1. A planilha é baixada no formato CSV pelo link público do Google Sheets.
2. Uma cópia fica guardada no servidor por 55 segundos, para não baixar a planilha a cada acesso.
3. A cada **60 segundos**, a página busca os dados novos e troca apenas o conteúdo: indicadores, cards, gráficos e tabela. A tela não pisca e os filtros continuam valendo.
4. Assim, **linhas novas na planilha viram cards novos sozinhas**, linhas apagadas somem e alterações aparecem em cerca de 1 minuto. O próprio Google pode levar mais um ou dois minutos para liberar uma edição recente.

A bolinha ao lado de "Atualizado em" indica o estado da atualização:
- 🟢 **verde, pulsando:** atualizando normalmente;
- 🔴 **vermelha:** a última tentativa falhou (internet ou Google fora do ar). O painel continua mostrando os últimos dados obtidos e volta a atualizar sozinho quando a conexão voltar.

Para forçar uma atualização na hora, use o link **"Atualizar agora"**.

---

## Instalação e execução

Requisitos: **Python 3.10+** e acesso à internet (a `docs.google.com`).

```powershell
# 1. Criar o ambiente virtual e instalar as dependências (só na primeira vez)
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt

# 2. Rodar
.\.venv\Scripts\python app.py
```

Depois, abra **http://localhost:8050** no navegador. Para acessar de outro computador ou da TV na mesma rede, use `http://<ip-desta-máquina>:8050`.

### Configuração (opcional)

As configurações são feitas por variáveis de ambiente, definidas antes de rodar:

| Variável | Padrão | Para que serve |
|---|---|---|
| `SHEET_ID` | ID da planilha de licitações | Planilha a ser exibida (o código longo na URL da planilha). |
| `SHEET_GID` | *(vazio = primeira aba)* | Aba da planilha (o número depois de `gid=` na URL). |
| `REFRESH` | `60` | Intervalo, em segundos, da atualização automática da tela. |
| `CACHE_TTL` | `REFRESH - 5` | Tempo, em segundos, que a cópia da planilha fica guardada no servidor. |
| `PORT` | `8050` | Porta do servidor. |

Exemplo, atualizando a cada 2 minutos na porta 8080:

```powershell
$env:REFRESH = "120"; $env:PORT = "8080"; .\.venv\Scripts\python app.py
```

> Evite intervalos muito curtos: o Google pode limitar downloads muito frequentes.

---

## Requisitos da planilha

- Deve estar compartilhada como **"Qualquer pessoa com o link pode ver"**.
- O cabeçalho é a **primeira linha que começa com `ID`**. As linhas acima dele são usadas no topo do painel: a primeira célula da linha logo acima é exibida como data de referência e as demais como equipes.
- As colunas são reconhecidas **pelo nome** (sem diferenciar acentos ou maiúsculas), então mudar a ordem ou ajustar levemente os nomes não quebra o painel. São usadas: ID, OBRAS, SECRETARIA, Nº SEI, RESPONSÁVEL, DATA ENVIO PROGE, DATA PUBLICAÇÃO EDITAL, DATA ABERTURA LICITAÇÃO, ATUALIZAÇÃO DAS FASES DO CERTAME, PRESIDENTE DA COMISSÃO, OBSERVAÇÃO, DATA HOMOLOGAÇÃO CERTAME, VALOR ORÇADO, VALOR VENCEDOR e ATUALIZADO EM, além da coluna marcada como **HABILITADO** na linha acima do cabeçalho.
- **Linhas sem o nome da obra são ignoradas.**
- **Células com `0` são tratadas como vazias.**
- **Fases** no formato `9 - FASE RECURSAL` são exibidas com o número em destaque e ordenadas por número nos gráficos.
- **Valores** no formato brasileiro (`R$ 1.234,56`) são reconhecidos. Se o valor vencedor tiver vários lotes (`LOTE 01: R$ ...; LOTE 02: R$ ...`), os lotes são somados.
- **O desconto é calculado pelo sistema** a partir dos valores orçado e vencedor, e não lido da coluna "% DESC.".
- **Uma coluna nova na planilha não aparece automaticamente nos cards:** é preciso incluí-la no código (veja abaixo).

---

## Estrutura do projeto

```
app.py                  # Leitura da planilha, tratamento dos dados e rotas
requirements.txt        # Dependências (Flask e requests)
static/style.css        # Estilos (inclui tema escuro e modo TV)
templates/
  base.html             # Cabeçalho, navegação, rodapé e atualização automática
  _card.html            # Card de um processo (usado por todas as exibições)
  dashboard.html        # Exibição "/"
  cards.html            # Exibição "/cards"
  secretarias.html      # Exibição "/secretarias"
  error.html            # Página exibida quando a planilha não pode ser lida
```

Também há a rota **`/api/licitacoes`**, que devolve os dados já tratados em JSON.

### Como adicionar uma nova exibição

1. Crie um template em `templates/` que estenda `base.html` e coloque o conteúdo dentro de `{% block content %}`. Marque com `data-live="algum-nome"` o elemento que deve ser trocado na atualização automática.
2. Crie a rota em `app.py`, usando `contexto()` para obter os dados:
   ```python
   @app.route("/minha-exibicao")
   def minha_exibicao():
       return render_template("minha_exibicao.html", **contexto())
   ```
3. Acrescente `("minha_exibicao", "Nome no menu")` à lista `VIEWS` em `app.py` para que ela apareça na navegação.

### Como exibir uma coluna nova da planilha

1. Em `app.py`, acrescente ao dicionário `FIELDS` um nome interno e um trecho do nome da coluna, por exemplo `"engenheiro": "engenheiro"`.
2. Use `{{ i.engenheiro }}` no template desejado, por exemplo em `_card.html`.

---

## Problemas comuns

| Sintoma | Causa provável / solução |
|---|---|
| *"Foi feita uma tentativa de acesso a um soquete de uma maneira que é proibida..."* ao iniciar | A porta já está em uso por outro programa. Use outra porta: `$env:PORT = "8080"`. |
| Página "Não foi possível carregar a planilha" | Sem internet, a planilha deixou de ser pública ou o firewall está bloqueando o acesso a `docs.google.com`. |
| *"Cabeçalho não encontrado"* | A planilha não tem mais uma linha começando com `ID`. |
| Uma alteração demora a aparecer | Normal até cerca de 1 a 2 minutos (intervalo de atualização somado ao atraso do Google). Use "Atualizar agora" para forçar. |
| Uma secretaria nova não aparece na lista do filtro | As listas dos filtros só são atualizadas ao recarregar a página (F5). Os cards e gráficos atualizam normalmente. |

---

Developed by D. Rohling ®
