@echo off
echo Inicializando repositório Git...
git init

echo Configurando usuário do Git...
git config user.email "seu.email@exemplo.com"
git config user.name "Seu Nome"

echo Adicionando arquivos...
git add .

echo Fazendo commit inicial...
git commit -m "Commit inicial: API de triagem para clínica odontológica"

echo.
echo Repositório Git inicializado com sucesso!
echo.
echo Próximos passos:
echo 1. Crie um repositório no GitHub/GitLab/Bitbucket
echo 2. Adicione o repositório remoto com: git remote add origin URL_DO_SEU_REPOSITORIO
echo 3. Faça o push: git push -u origin main

pause
