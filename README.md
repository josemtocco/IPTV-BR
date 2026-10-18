# 📺 IPTV Brasil — Lista otimizada para SS IPTV

Lista M3U de canais brasileiros **gratuitos e públicos**, otimizada para o aplicativo **SS IPTV**.

- Fonte de dados: [iptv-org](https://github.com/iptv-org/iptv) (mesma base do [brazil-stream-finder.lovable.app](https://brazil-stream-finder.lovable.app/))
- Atualização automática a cada **6 horas** via GitHub Actions
- **Não remove** canais que ainda funcionam
- Só remove um canal se ele falhar em **3 atualizações consecutivas**
- Mantém histórico de canais que já funcionaram (mesmo que saiam da fonte oficial)
- Categorias em português, logos e `tvg-id` para EPG

---

## 🔗 Link da lista (cole no SS IPTV)

Após publicar o repositório no GitHub, use o link **Raw**:

```
https://raw.githubusercontent.com/SEU-USUARIO/SEU-REPO/main/playlist.m3u
```

Exemplo (troque pelo seu):

```
https://raw.githubusercontent.com/seu-usuario/iptv-br-ssiptv/main/playlist.m3u
```

### Como adicionar no SS IPTV

1. Abra o SS IPTV
2. Vá em **Configurações → Listas de canais / Playlists**
3. Adicione nova lista → cole a URL acima
4. Salve e atualize a lista

---

## 🚀 Como implantar no seu GitHub (passo a passo)

1. Crie um repositório **público** no GitHub (ex: `iptv-br-ssiptv`)
2. Faça upload de todos os arquivos desta pasta:
   - `update.py`
   - `playlist.m3u` (será gerado/atualizado automaticamente)
   - `state.json` (será gerado automaticamente)
   - `.github/workflows/update.yml`
   - `README.md`
3. No repositório, vá em **Settings → Actions → General** e permita que Actions façam commit:
   - *Workflow permissions* → **Read and write permissions**
4. Rode o workflow manualmente uma vez:
   - Aba **Actions** → *Atualizar lista IPTV Brasil* → **Run workflow**
5. Pronto! A lista será atualizada sozinha a cada 6 horas.

---

## ⚙️ Política de remoção de canais

| Situação                         | Ação                          |
|----------------------------------|-------------------------------|
| Canal funciona na atualização    | `fail_count = 0` (mantém)     |
| Canal falha                      | `fail_count += 1`             |
| `fail_count < 3`                 | **Mantém** na lista           |
| `fail_count >= 3`                | **Remove** da lista           |
| Canal some da fonte, mas ainda funciona | **Mantém** (histórico) |

Isso evita que canais “pisquem” (ontem funcionava, hoje não, amanhã volta) e some da sua lista.

---

## 🛠️ Rodar localmente (opcional)

```bash
pip install requests urllib3
python update.py
```

Gera/atualiza `playlist.m3u` e `state.json`.

---

## 📋 O que a lista contém

- Canais abertos brasileiros (Band, TV Brasil, Record, Globo regionais, legislativos, universitários, agro, etc.)
- Alguns canais latinos disponíveis no Brasil
- Grupos em português: Notícias, Esportes, Geral, Filmes, Infantil...
- Suporte a EPG (`x-tvg-url` apontando para o guia do iptv-org)

---

## ⚠️ Aviso legal

Esta lista apenas agrega **links públicos** já disponíveis na internet (fonte: projeto iptv-org).  
Não hospedamos streams. Respeite as leis locais e os termos de uso de cada emissora.

---

Atualizado automaticamente pelo GitHub Actions.
