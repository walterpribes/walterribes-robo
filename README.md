# Robô do @walterribestrafego

Dois robôs que rodam sozinhos no GitHub, com o mesmo token da Meta:

1. **Posts**: publica no Instagram, no dia e na hora marcados em `posts.json`, posts de foto, carrosséis,
   **Reels** e stories. Se você marcar, também publica no Facebook (só fotos).
2. **Anúncios**: cria no Gerenciador de Anúncios campanhas para **chamar no Direct**, usando um post seu.
   Tudo nasce **PAUSADO**. Só gasta dinheiro depois que você manda **ativar**.

---

## Como usar no dia a dia

### Agendar um post
1. Suba o arquivo para `media/`. Foto tem que ser **JPEG**. Reel é **MP4 9:16** de até 90 s.
2. Acrescente um item em `posts.json`:
```json
{
  "date": "2026-11-12", "time": "18:00",
  "tipo": "reel",
  "arquivos": ["media/reels/meu-video.mp4"],
  "capa": "media/reels/minha-capa.jpg",
  "legenda": "Texto da legenda…",
  "facebook": false
}
```
- `tipo`: `post` (1 foto), `carrossel` (2 a 10 fotos), `reel` (1 vídeo) ou `story` (1 foto ou vídeo).
- `capa` é opcional e só vale para Reels.

O robô confere o calendário a cada 15 minutos, das 7h às 23h, e **nunca publica o mesmo post duas vezes**.
O que já saiu fica registrado em `publicados.json`.

### Anunciar um post (conversas no Direct)
1. Acrescente um item em `anuncios.json`:
```json
{
  "nome": "site-trafego-500",
  "post": "2026-11-10 18:00",
  "orcamento_diario": 20,
  "inicio": "2026-11-11", "fim": "2026-11-17",
  "local": {"nome": "Brasília", "lat": -15.7939, "lng": -47.8828, "raio_km": 30},
  "idade_min": 25, "idade_max": 60,
  "publico_automatico": false
}
```
- `post` é a data e hora do post no `posts.json`, que precisa já ter sido publicado.
  Para anunciar um post antigo, use `"ig_media_id": "id do post"` no lugar de `post`.
- `orcamento_diario` é em reais. O gasto máximo é o orçamento diário × os dias. Há uma trava de **R$ 100/dia**.
- `publico_automatico: true` deixa a Meta ampliar o público além de idade e raio.
2. **Actions → Anúncios Meta → Run workflow**:
   - `simular`: mostra o que vai ser criado e quanto pode gastar. Não cria nada.
   - `criar`: cria campanha, conjunto e anúncio **pausados**. Confira no Gerenciador de Anúncios.
   - `ativar` + nome do anúncio: liga o anúncio. A Meta revisa e ele começa a rodar e **gastar**.
   - `pausar`: pausa um anúncio (ou todos, deixando o nome vazio).
   - `relatorio`: gasto, alcance e conversas no Direct. Também roda sozinho todo dia às 8h,
     aparece no resumo da execução e não fica salvo no repositório.

---

## Configuração (uma vez só)

### 1. Contas na Meta
- O **@walterribestrafego** tem que ser conta **Comercial**, não Criador. Mude em Instagram → Configurações →
  Tipo de conta e ferramentas.
- Ele precisa estar **ligado a uma Página do Facebook**. Se ainda não tiver Página, crie uma
  ("Walter Ribes · Tráfego e Sites") e conecte o Instagram em Configurações da Página → Contas vinculadas.
- No **Meta Business Suite** (business.facebook.com) → Configurações, no **seu** portfólio, devem estar:
  a Página, o Instagram e uma **conta de anúncios** em reais, fuso de São Paulo e com **forma de pagamento**
  cadastrada.
- Anote o **número da conta de anúncios**, que aparece no Gerenciador de Anúncios como `act_123…`.

### 2. Token
1. Use o **mesmo app** do Jotaká em developers.facebook.com. Não precisa criar outro.
2. No **Explorador da Graph API**, escolha o app e marque estas permissões:
   `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `instagram_basic`,
   `instagram_content_publish`, `business_management`, `ads_management`, `ads_read`, `pages_manage_ads`.
3. **Gerar token de acesso** → autorize **a sua Página e o seu Instagram**, não os do Jotaká.
4. No **Depurador de token** → **Estender token de acesso** → copie o token longo.
5. No Explorador, cole o token longo e faça `GET me/accounts`. Na linha da **sua** Página, copie o
   `access_token`. Esse é o token da Página, que não expira.

### 3. Guardar no GitHub
Neste repositório: **Settings → Secrets and variables → Actions → New repository secret**
- `META_PAGE_TOKEN`: o token da Página do passo 2.5.
- `META_AD_ACCOUNT`: o número da conta de anúncios, só os dígitos, sem `act_`.

O token nunca aparece no código nem nos registros. Lá ele vira `***`.

### 4. Testar sem publicar e sem gastar
- **Actions → Posts → Run workflow → `check`**: confere o token, a Página e o Instagram.
- **Actions → Posts → Run workflow → `dry-run`**: manda o próximo post para o Instagram processar, sem publicar.
- **Actions → Anúncios Meta → Run workflow → `check`**: confere a conta de anúncios.

Se os três ficarem verdes, está tudo pronto.
