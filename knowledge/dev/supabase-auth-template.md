# Template de Autenticação Supabase

## Configuração do Cliente Supabase
A inicialização do Supabase utiliza `@supabase/ssr` para gerenciar cookies de sessão com segurança em Server e Client Components.
As credenciais públicas `NEXT_PUBLIC_SUPABASE_URL` e `NEXT_PUBLIC_SUPABASE_ANON_KEY` residem em variáveis de ambiente.

## Políticas de Row Level Security (RLS)
Todas as tabelas de dados de clientes no PostgreSQL do Supabase devem habilitar RLS obrigatoriamente.
Políticas devem isolar o acesso por `auth.uid() = user_id`.
