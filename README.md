# Clareia

A Clareia usa FastAPI para servir o front-end e a API no mesmo endereço. A rota
`POST /api/simplify` envia o texto ao Gemini e `GET /health` verifica o serviço.
O modelo padrão é `gemini-3.5-flash-lite`; para trocar, defina a variável de
ambiente `MODEL_NAME` e reinicie o servidor.

## Configurar no Replit

1. Abra **Tools → Secrets**.
2. Adicione `GEMINI_API_KEY` com uma chave válida da API Gemini.
3. Inicie a aplicação pelo workflow **Clareia**.

A chave fica somente no servidor. Se estiver ausente, o servidor registra um
aviso ao iniciar e a simplificação informa que ainda não está configurada.

## Rodar localmente

Instale as dependências com `pip install -r requirements.txt`. Gere os arquivos
estáticos com `pnpm --filter @workspace/clareia run build` e inicie o servidor:

```sh
python -m uvicorn backend.main:app --app-dir artifacts/clareia \
  --host 0.0.0.0 --port 8000 --no-access-log
```

## Testes

```sh
cd artifacts/clareia
python -m unittest discover -s tests -v
```

O servidor registra apenas data/hora, status HTTP e tamanho do texto; não
registra o conteúdo enviado nem o resultado gerado.
