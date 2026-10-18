# xdllp

Bot do Telegram que recebe o link de um post do X (Twitter) e devolve o vídeo direto no chat. Usa a API do Telegram via MTProto (Telethon), então envia arquivos de até 2 GB, em vez do limite de 50 MB da Bot API comum.

## Como funciona

1. Você envia o link de um post do X com vídeo.
2. O bot busca o vídeo pelo fxtwitter e, se falhar, pelo yt-dlp.
3. Baixa o arquivo para uma pasta temporária.
4. Envia para o chat mostrando o progresso do upload e apaga o arquivo depois.

## Requisitos

- Python 3.9 ou superior
- Um bot criado no @BotFather
- `API_ID` e `API_HASH` de https://my.telegram.org (em **API development tools**)

## Estrutura

```
bot.py
requirements.txt
.env
.gitignore
```

## Configuração

Crie o arquivo `.env` na mesma pasta do `bot.py`:

```
API_ID=123456
API_HASH=seu_api_hash
BOT_TOKEN=seu_token
ALLOWED_IDS=
```

| Variável | Descrição |
|---|---|
| `API_ID` | ID do app em my.telegram.org |
| `API_HASH` | Hash do app em my.telegram.org |
| `BOT_TOKEN` | Token do @BotFather |
| `ALLOWED_IDS` | Opcional. IDs numéricos autorizados, separados por vírgula. Vazio libera para todos. Descubra o seu no @userinfobot |

`requirements.txt`:

```
telethon
cryptg
hachoir
requests
yt-dlp
```

`.gitignore`:

```
.env
*.session
*.session-journal
venv/
__pycache__/
```

> Nunca suba o `.env` nem o arquivo `.session` para o GitHub. Eles guardam suas credenciais e o login do bot.

## Termux (Android)

1. Instale o Termux pelo **F-Droid** ou GitHub, não pela Play Store.
2. Instale os pacotes:

```
pkg update && pkg upgrade
pkg install python git tmux
pip install telethon requests yt-dlp hachoir
```

3. Opcional, para acelerar o upload (se der erro na compilação, ignore):

```
pkg install rust binutils clang
pip install cryptg
```

4. Coloque os arquivos em uma pasta (por exemplo `~/xbot`) e crie o `.env` com `nano .env`.
5. Rode:

```
cd ~/xbot
termux-wake-lock
tmux new -s bot
python bot.py
```

6. Controles do tmux:

| Ação | Comando |
|---|---|
| Sair sem parar o bot | `Ctrl+B` e depois `D` |
| Voltar ao console | `tmux attach -t bot` |
| Parar o bot | `Ctrl+C` dentro do tmux |

7. Nas configurações do Android, em Apps > Termux > Bateria, escolha **Sem restrições**. Sem isso o sistema pode matar o bot em segundo plano.

### Iniciar sozinho ao ligar o celular

Instale o app **Termux:Boot** (F-Droid) e crie o arquivo `~/.termux/boot/bot.sh`:

```
termux-wake-lock
tmux new -d -s bot 'cd ~/xbot && python bot.py'
```

Depois rode `chmod +x ~/.termux/boot/bot.sh` e abra o Termux:Boot uma vez.

## VS Code / Linux / Windows

1. Abra a pasta no VS Code e, no terminal, crie o ambiente virtual:

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

No Windows, a ativação é `venv\Scripts\activate`. Se o `cryptg` falhar, remova-o do `requirements.txt` e instale o resto.

2. Crie o `.env`.
3. Rode:

```
python bot.py
```

4. Para deixar em segundo plano no Linux, use `tmux new -s bot` e rode o bot dentro dele. Em servidores, um serviço `systemd` também funciona.

## Uso

Envie `/start` para ver a mensagem inicial e depois mande o link de um post, por exemplo:

```
https://x.com/usuario/status/1234567890
```

## Manutenção

| Situação | O que fazer |
|---|---|
| Atualizar o código | `git pull` e reiniciar o bot |
| Parou de baixar vídeos | `pip install -U yt-dlp` |
| Bibliotecas sumiram após atualizar o Python | `pip install -r requirements.txt` (no Termux, sem o `cryptg` se ele não compilar) |
| Erro de variável ausente | Confira se o `.env` está na mesma pasta do `bot.py` e com o nome certo |

## Problemas comuns

- **Fica em "Enviando..." sem avançar:** o upload é lento sem o `cryptg`, principalmente no celular. Veja a porcentagem na mensagem e no console. Se ela sobe, é só esperar.
- **Erro 409 ou o bot não responde:** o mesmo `BOT_TOKEN` está ativo em outro lugar. Rode o bot em um único dispositivo por vez.
- **"Não achei vídeo nesse post":** o post pode não ter vídeo, ou exigir login (conteúdo sensível). O bot não usa cookies.
- **O bot morre sozinho no Android:** desative a otimização de bateria do Termux e use o `termux-wake-lock`.

## Limites

- Tamanho máximo de 2 GB por vídeo.
- O arquivo `bot_session.session` guarda o login do bot. Se apagar, o bot só faz login de novo.