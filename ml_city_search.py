"""
Mercado Livre - Buscador por Cidade
Gera links filtrados por cidade para encontrar vendedores locais.

Como funciona:
- Usa os IDs internos do Mercado Livre codificados em base64
- O ID real de Uberlândia foi extraído da URL original fornecida
- Para outras cidades: cole uma URL de busca do ML com filtro de cidade
  e o app extrai automaticamente o city_id e state_id
"""

import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
import urllib.parse
import json
import base64
import re
import threading
import urllib.request

# ─────────────────────────────────────────────────────────────────────────────
# BASE DE DADOS DE CIDADES — IDs reais extraídos de URLs do Mercado Livre
# Formato: "Cidade (UF)": {
#   "city_id":    ID interno do ML para a cidade,
#   "state_id":   ID interno do ML para o estado,
#   "state_name": nome do estado para exibição
# }
# ─────────────────────────────────────────────────────────────────────────────
CIDADES: dict[str, dict] = {
    # ── Minas Gerais ──────────────────────────────────────────────────────────
    "Uberlândia (MG)": {
        "city_id":    "MLBCUBEa8a56",
        "state_id":   "MLBPMINS1502d",
        "state_name": "Minas Gerais",
        "city_name":  "Uberlândia",
    },
    # As demais cidades serão populadas via "Importar URL do ML"
    # ou adicionadas manualmente pelo usuário
}

CIDADE_PADRAO = "Uberlândia (MG)"

# ─────────────────────────────────────────────────────────────────────────────
# MAPEAMENTO: nome de exibição → filtro na URL
# ─────────────────────────────────────────────────────────────────────────────
CONDICOES = {
    "Qualquer condição": "",
    "Novo":              "novo",
    "Usado":             "usado",
}

ORDENACAO = {
    "Mais relevantes":   "",
    "Menor preço":       "price_asc",
    "Maior preço":       "price_desc",
    "Mais vendidos":     "sales_asc",
    "Recém adicionados": "date_asc",
    "Melhor avaliados":  "rating_desc",
}


# ─────────────────────────────────────────────────────────────────────────────
# FUNÇÕES DE URL
# ─────────────────────────────────────────────────────────────────────────────
def encode_ml_id(raw_id: str) -> str:
    """Codifica um ID interno do ML em base64 sem padding '='."""
    encoded = base64.b64encode(raw_id.encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def decode_ml_id(b64: str) -> str:
    """Decodifica um ID base64 do ML (sem padding) para o ID interno."""
    padding = "=" * (4 - len(b64) % 4) if len(b64) % 4 else ""
    return base64.b64decode(b64 + padding).decode("utf-8")


def extrair_ids_da_url(url: str) -> dict | None:
    """
    Extrai city_id, state_id e city_name de uma URL de busca do ML
    que já contenha filtro de cidade.
    Retorna dict ou None se não encontrar.
    """
    # Padrão: _pickup*city_XXXX_pickup*state_YYYY
    path_match = re.search(r"pickup\*city_([A-Za-z0-9+/]+=*)_pickup\*state_([A-Za-z0-9+/]+=*)", url)

    # Padrão no fragment: applied_value_id%3DXXXX e applied_value_name%3DYYYY
    frag_city_id_match   = re.search(r"applied_value_id(?:%3D|=)([A-Za-z0-9+/]+=*)", url)
    frag_city_name_match = re.search(r"applied_value_name(?:%3D|=)((?:(?!%26|&).)+)", url)

    # Padrão state no fragment: pickup_state no path
    frag_state_match = re.search(r"pickup\*state_([A-Za-z0-9+/]+=*)", url)

    if not path_match and not frag_city_id_match:
        return None

    city_b64  = (path_match.group(1) if path_match else frag_city_id_match.group(1))
    state_b64 = (path_match.group(2) if path_match else
                 (frag_state_match.group(1) if frag_state_match else ""))

    city_id  = decode_ml_id(city_b64)
    state_id = decode_ml_id(state_b64) if state_b64 else ""

    city_name = ""
    if frag_city_name_match:
        city_name = urllib.parse.unquote_plus(frag_city_name_match.group(1))

    return {
        "city_id":   city_id,
        "state_id":  state_id,
        "city_name": city_name,
    }


def build_url(
    produto: str,
    cidade_key: str,
    condicao: str,
    ordenacao: str,
    preco_min: str,
    preco_max: str,
    com_frete_gratis: bool,
    com_frete_full: bool,
    apenas_loja_oficial: bool,
    avaliacao_min: str,
) -> str:
    """Monta a URL de busca do Mercado Livre filtrada por cidade."""
    dados      = CIDADES[cidade_key]
    city_id    = dados["city_id"]
    state_id   = dados["state_id"]
    city_name  = dados.get("city_name", cidade_key.split(" (")[0])

    city_b64  = encode_ml_id(city_id)
    state_b64 = encode_ml_id(state_id) if state_id else ""

    # Slug do produto
    produto_slug = urllib.parse.quote(
        produto.strip().lower().replace(" ", "-"), safe="-"
    )

    # Parte de condição na URL
    cond_part = f"/{condicao}" if condicao else ""

    # Monta caminho base
    state_part = f"_pickup*state_{state_b64}" if state_b64 else ""
    url = (
        f"https://lista.mercadolivre.com.br/{produto_slug}"
        f"_NoIndex_True"
        f"_SHIPPING*ORIGIN_10215068"
        f"_pickup*city_{city_b64}"
        f"{state_part}"
        f"{cond_part}"
    )

    # Query string com filtros extras
    params: dict[str, str] = {}

    if ordenacao:
        params["sort"] = ordenacao

    # Preço
    pmin = preco_min.strip().replace(",", ".") if preco_min else ""
    pmax = preco_max.strip().replace(",", ".") if preco_max else ""
    if pmin and pmax:
        params["price"] = f"{pmin}-{pmax}"
    elif pmin:
        params["price"] = f"{pmin}-*"
    elif pmax:
        params["price"] = f"*-{pmax}"

    if com_frete_gratis:
        params["shipping"] = "free"
    if com_frete_full:
        params["SHIPPING*origin"] = "10215068"  # Mercado Envios Full

    if params:
        url += "?" + urllib.parse.urlencode(params)

    # Fragment — mantém compatibilidade com o filtro de cidade do ML
    city_name_encoded  = urllib.parse.quote(city_name)
    fragment = (
        f"applied_filter_id%3Dpickup_city"
        f"%26applied_filter_name%3DRetirada+gr%C3%A1tis%3A+Cidade"
        f"%26applied_filter_order%3D6"
        f"%26applied_value_id%3D{city_b64}"
        f"%26applied_value_name%3D{city_name_encoded}"
        f"%26applied_value_order%3D4"
        f"%26applied_value_results%3D1"
        f"%26is_custom%3Dfalse"
    )
    url += "#" + fragment
    return url


# ─────────────────────────────────────────────────────────────────────────────
# JANELA: Importar cidade a partir de URL
# ─────────────────────────────────────────────────────────────────────────────
class ImportarCidadeDialog(tk.Toplevel):
    def __init__(self, parent: "App"):
        super().__init__(parent)
        self.parent = parent
        self.title("📥 Importar cidade de URL do ML")
        self.geometry("640x340")
        self.resizable(False, False)
        self.configure(bg="#FFFFFF")
        self.grab_set()

        tk.Label(
            self,
            text=(
                "Cole abaixo uma URL do Mercado Livre que já tenha\n"
                "o filtro de cidade aplicado (ex.: a URL que você forneceu)."
            ),
            font=("Segoe UI", 10), bg="#FFFFFF", justify="left"
        ).pack(padx=16, pady=(16, 8), anchor="w")

        self.url_text = tk.Text(self, height=5, font=("Consolas", 9), wrap="word")
        self.url_text.pack(fill="x", padx=16, pady=(0, 8))
        self.url_text.insert("1.0", "https://lista.mercadolivre.com.br/")

        tk.Label(self, text="Nome para exibição (ex.: São Paulo (SP)):",
                 font=("Segoe UI", 10), bg="#FFFFFF").pack(padx=16, anchor="w")
        self.nome_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.nome_var, width=40,
                  font=("Segoe UI", 11)).pack(padx=16, pady=(4, 12), anchor="w", ipady=4)

        tk.Label(self, text="Nome do Estado (ex.: São Paulo):",
                 font=("Segoe UI", 10), bg="#FFFFFF").pack(padx=16, anchor="w")
        self.estado_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.estado_var, width=30,
                  font=("Segoe UI", 11)).pack(padx=16, pady=(4, 12), anchor="w", ipady=4)

        self.status_lbl = tk.Label(self, text="", font=("Segoe UI", 9),
                                   bg="#FFFFFF", fg="#E00000")
        self.status_lbl.pack(padx=16, anchor="w")

        btn_frame = tk.Frame(self, bg="#FFFFFF")
        btn_frame.pack(fill="x", padx=16, pady=(8, 16))
        ttk.Button(btn_frame, text="✅ Importar", command=self._importar).pack(side="left", padx=(0, 8))
        ttk.Button(btn_frame, text="❌ Cancelar", command=self.destroy).pack(side="left")

    def _importar(self):
        url  = self.url_text.get("1.0", "end").strip()
        nome = self.nome_var.get().strip()
        est  = self.estado_var.get().strip()

        if not url or not nome:
            self.status_lbl.config(text="❗ Preencha a URL e o nome de exibição.")
            return

        resultado = extrair_ids_da_url(url)
        if not resultado:
            self.status_lbl.config(
                text="❗ Não foi possível extrair os IDs de cidade.\n"
                     "Certifique-se que a URL tem o filtro de cidade aplicado."
            )
            return

        city_name = resultado["city_name"] or nome.split(" (")[0]
        CIDADES[nome] = {
            "city_id":    resultado["city_id"],
            "state_id":   resultado["state_id"],
            "state_name": est,
            "city_name":  city_name,
        }

        # Atualiza combobox na janela principal
        self.parent.atualizar_lista_cidades(selecionar=nome)
        messagebox.showinfo(
            "Cidade importada!",
            f"'{nome}' foi adicionada com sucesso!\n\n"
            f"City ID:  {resultado['city_id']}\n"
            f"State ID: {resultado['state_id']}",
            parent=self
        )
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
# JANELA PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🛒 ML Buscador por Cidade")
        self.geometry("700x660")
        self.resizable(False, False)
        self.configure(bg="#FFF159")

        self._build_header()
        self._build_body()
        self._build_footer()

    # ── Header ───────────────────────────────────────────────────────────────
    def _build_header(self):
        hdr = tk.Frame(self, bg="#FFF159", pady=12)
        hdr.pack(fill="x")

        tk.Label(
            hdr, text="🛒 Mercado Livre — Buscador por Cidade",
            font=("Segoe UI", 18, "bold"), bg="#FFF159", fg="#1A1A1A"
        ).pack()
        tk.Label(
            hdr, text="Encontre vendedores e produtos em cidades específicas",
            font=("Segoe UI", 10), bg="#FFF159", fg="#555"
        ).pack()

    # ── Body ─────────────────────────────────────────────────────────────────
    def _build_body(self):
        body = tk.Frame(self, bg="#FFFFFF", padx=24, pady=16)
        body.pack(fill="both", expand=True, padx=14, pady=(0, 0))
        self.body = body
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, weight=1)

        row = 0

        # ── Produto ──────────────────────────────────────────────────────────
        self._lbl(body, "🔍  Produto", row); row += 1
        self.produto_var = tk.StringVar()
        entry = ttk.Entry(body, textvariable=self.produto_var,
                          font=("Segoe UI", 13), width=46)
        entry.grid(row=row, column=0, columnspan=3, sticky="ew",
                   pady=(0, 10), ipady=6)
        entry.focus_set()
        row += 1

        # ── Cidade ───────────────────────────────────────────────────────────
        city_lbl_frame = tk.Frame(body, bg="#FFFFFF")
        city_lbl_frame.grid(row=row, column=0, columnspan=3, sticky="ew",
                            pady=(4, 2))
        tk.Label(city_lbl_frame, text="📍  Cidade", font=("Segoe UI", 10, "bold"),
                 bg="#FFFFFF", fg="#333").pack(side="left")
        ttk.Button(city_lbl_frame, text="+ Importar cidade de URL",
                   command=self._abrir_importar, cursor="hand2"
                   ).pack(side="right")
        row += 1

        self.cidade_var = tk.StringVar(value=CIDADE_PADRAO)
        self.cb_cidade = ttk.Combobox(
            body, textvariable=self.cidade_var,
            values=sorted(CIDADES.keys()),
            state="normal", font=("Segoe UI", 12), width=44
        )
        self.cb_cidade.grid(row=row, column=0, columnspan=3, sticky="ew",
                            pady=(0, 10), ipady=4)
        self.cb_cidade.bind("<KeyRelease>", self._filtrar_cidades)
        row += 1

        # ── Condição ─────────────────────────────────────────────────────────
        self._lbl(body, "📦  Condição", row); row += 1
        self.cond_var = tk.StringVar(value="Qualquer condição")
        for i, cond in enumerate(CONDICOES.keys()):
            ttk.Radiobutton(body, text=cond,
                            variable=self.cond_var, value=cond
                            ).grid(row=row, column=i, sticky="w", padx=(0, 10))
        row += 1

        # ── Ordenação ────────────────────────────────────────────────────────
        self._lbl(body, "📊  Ordenar por", row); row += 1
        self.ordem_var = tk.StringVar(value="Mais relevantes")
        ttk.Combobox(
            body, textvariable=self.ordem_var,
            values=list(ORDENACAO.keys()),
            state="readonly", font=("Segoe UI", 11), width=28
        ).grid(row=row, column=0, columnspan=2, sticky="w",
               pady=(0, 10), ipady=3)
        row += 1

        # ── Filtros adicionais ────────────────────────────────────────────────
        self._lbl(body, "⚙️  Filtros adicionais", row); row += 1

        filtros_frame = tk.Frame(body, bg="#F7F7F7", bd=1, relief="groove",
                                 padx=14, pady=12)
        filtros_frame.grid(row=row, column=0, columnspan=3, sticky="ew",
                           pady=(0, 10))
        filtros_frame.columnconfigure(0, weight=1)
        filtros_frame.columnconfigure(1, weight=1)
        filtros_frame.columnconfigure(2, weight=1)
        row += 1

        # Preços
        tk.Label(filtros_frame, text="Preço mínimo (R$):",
                 font=("Segoe UI", 9), bg="#F7F7F7").grid(row=0, column=0, sticky="w")
        tk.Label(filtros_frame, text="Preço máximo (R$):",
                 font=("Segoe UI", 9), bg="#F7F7F7").grid(row=0, column=1, sticky="w")
        tk.Label(filtros_frame, text="Avaliação mínima:",
                 font=("Segoe UI", 9), bg="#F7F7F7").grid(row=0, column=2, sticky="w")

        self.preco_min_var = tk.StringVar()
        self.preco_max_var = tk.StringVar()
        self.avaliacao_var = tk.StringVar(value="Qualquer")

        ttk.Entry(filtros_frame, textvariable=self.preco_min_var,
                  width=12, font=("Segoe UI", 10)
                  ).grid(row=1, column=0, sticky="w", pady=(2, 10), ipady=3)
        ttk.Entry(filtros_frame, textvariable=self.preco_max_var,
                  width=12, font=("Segoe UI", 10)
                  ).grid(row=1, column=1, sticky="w", pady=(2, 10), ipady=3)
        ttk.Combobox(
            filtros_frame, textvariable=self.avaliacao_var,
            values=["Qualquer", "⭐⭐⭐⭐⭐ 5 estrelas", "⭐⭐⭐⭐ 4+ estrelas",
                    "⭐⭐⭐ 3+ estrelas"],
            state="readonly", width=16, font=("Segoe UI", 9)
        ).grid(row=1, column=2, sticky="w", pady=(2, 10), ipady=3)

        # Checkboxes
        self.frete_var  = tk.BooleanVar(value=False)
        self.full_var   = tk.BooleanVar(value=False)
        self.loja_var   = tk.BooleanVar(value=False)

        ttk.Checkbutton(filtros_frame, text="🚚 Frete grátis",
                        variable=self.frete_var
                        ).grid(row=2, column=0, sticky="w", pady=(0, 4))
        ttk.Checkbutton(filtros_frame, text="⚡ Mercado Envios Full",
                        variable=self.full_var
                        ).grid(row=2, column=1, sticky="w", pady=(0, 4))
        ttk.Checkbutton(filtros_frame, text="🏪 Loja oficial",
                        variable=self.loja_var
                        ).grid(row=2, column=2, sticky="w", pady=(0, 4))

        # Opções de comportamento
        self.show_url_var   = tk.BooleanVar(value=False)
        self.confirm_var    = tk.BooleanVar(value=False)

        ttk.Checkbutton(filtros_frame, text="🔗 Exibir URL gerada",
                        variable=self.show_url_var
                        ).grid(row=3, column=0, sticky="w")
        ttk.Checkbutton(filtros_frame, text="❓ Confirmar antes de abrir",
                        variable=self.confirm_var
                        ).grid(row=3, column=1, sticky="w")

    # ── Footer ────────────────────────────────────────────────────────────────
    def _build_footer(self):
        footer = tk.Frame(self, bg="#FFF159", pady=10)
        footer.pack(fill="x", padx=14)

        self.btn_buscar = tk.Button(
            footer,
            text="🚀  BUSCAR NO MERCADO LIVRE",
            font=("Segoe UI", 13, "bold"),
            bg="#3483FA", fg="#FFFFFF",
            activebackground="#2968C8", activeforeground="#FFFFFF",
            relief="flat", cursor="hand2", bd=0,
            padx=20, pady=12,
            command=self._buscar
        )
        self.btn_buscar.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_copiar = tk.Button(
            footer,
            text="📋 Copiar link",
            font=("Segoe UI", 11),
            bg="#EEEEEE", fg="#333333",
            activebackground="#DDDDDD", activeforeground="#333333",
            relief="flat", cursor="hand2", bd=0,
            padx=14, pady=12,
            command=self._copiar_link
        )
        self.btn_copiar.pack(side="left")

        # Bind Enter key
        self.bind("<Return>", lambda e: self._buscar())

        # Preview da URL
        self.url_preview = tk.Label(
            self, text="", wraplength=670,
            font=("Consolas", 8), bg="#FFF159", fg="#666",
            justify="left", anchor="w", padx=14
        )
        self.url_preview.pack(fill="x", pady=(0, 8))

    # ── Utilitários de UI ─────────────────────────────────────────────────────
    def _lbl(self, parent, text, row):
        tk.Label(
            parent, text=text,
            font=("Segoe UI", 10, "bold"),
            bg="#FFFFFF", fg="#222", anchor="w"
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(10, 2))

    def _filtrar_cidades(self, event=None):
        termo = self.cidade_var.get().lower()
        filtradas = sorted(c for c in CIDADES if termo in c.lower())
        self.cb_cidade["values"] = filtradas or sorted(CIDADES.keys())

    def atualizar_lista_cidades(self, selecionar: str = ""):
        self.cb_cidade["values"] = sorted(CIDADES.keys())
        if selecionar:
            self.cidade_var.set(selecionar)

    def _abrir_importar(self):
        ImportarCidadeDialog(self)

    # ── Lógica de busca ───────────────────────────────────────────────────────
    def _get_url(self) -> str | None:
        produto = self.produto_var.get().strip()
        if not produto:
            messagebox.showwarning("Campo vazio",
                                   "Digite o nome do produto para buscar.")
            return None

        cidade = self.cidade_var.get().strip()
        if cidade not in CIDADES:
            matches = [c for c in CIDADES if cidade.lower() in c.lower()]
            if matches:
                cidade = matches[0]
                self.cidade_var.set(cidade)
            else:
                messagebox.showerror(
                    "Cidade não encontrada",
                    f"'{cidade}' não está na lista.\n\n"
                    "Use o botão '+ Importar cidade de URL' para adicionar\n"
                    "novas cidades a partir de uma URL do Mercado Livre."
                )
                return None

        return build_url(
            produto       = produto,
            cidade_key    = cidade,
            condicao      = CONDICOES[self.cond_var.get()],
            ordenacao     = ORDENACAO[self.ordem_var.get()],
            preco_min     = self.preco_min_var.get(),
            preco_max     = self.preco_max_var.get(),
            com_frete_gratis   = self.frete_var.get(),
            com_frete_full     = self.full_var.get(),
            apenas_loja_oficial = self.loja_var.get(),
            avaliacao_min = self.avaliacao_var.get(),
        )

    def _buscar(self):
        url = self._get_url()
        if not url:
            return

        if self.show_url_var.get():
            self.url_preview.config(text=f"URL: {url}")

        if self.confirm_var.get():
            resp = messagebox.askyesno(
                "Confirmar abertura",
                f"Abrir no navegador?\n\n{url[:120]}{'...' if len(url)>120 else ''}"
            )
            if not resp:
                return

        webbrowser.open(url)
        self.url_preview.config(
            text=f"✅ Aberto: {url[:80]}..." if len(url) > 80 else f"✅ Aberto: {url}"
        )

    def _copiar_link(self):
        url = self._get_url()
        if not url:
            return
        self.clipboard_clear()
        self.clipboard_append(url)
        self.url_preview.config(text=f"📋 Copiado: {url[:80]}...")
        messagebox.showinfo("Copiado!", "Link copiado para a área de transferência.")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()
