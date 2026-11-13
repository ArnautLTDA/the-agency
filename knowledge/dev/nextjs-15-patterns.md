# Padrões de Desenvolvimento Next.js 15 App Router

## Estrutura de Rotas e Route Handlers
No Next.js 15, rotas de API residem no diretório `app/api/.../route.ts`.
Todos os handlers devem utilizar as assinaturas assíncronas padrão: `GET(request: Request)` e `POST(request: Request)`.
Sempre retornar instâncias de `NextResponse.json(...)` com status HTTP explícito.

## Server Components vs Client Components
Por padrão, todos os componentes são Server Components.
Utilize a diretiva `'use client'` apenas quando houver necessidade de interatividade com hooks (`useState`, `useEffect`) ou eventos de clique.

## Imutabilidade e Manipulação de Estado
Sempre retorne novos objetos e arrays imutáveis em funções de transformação e handlers.
Nunca altere o estado do componente por mutação direta.
