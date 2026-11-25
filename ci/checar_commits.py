"""Valida mensagens no padrão Conventional Commits. Usos:
  python ci/checar_commits.py HEAD~10..HEAD      (histórico)
  ci/hooks/commit-msg                            (hook local: copie para .git/hooks/commit-msg)
"""
import re
import subprocess
import sys

PADRAO = re.compile(r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-z0-9_-]+\))?(!)?: \S.{2,}$")


def valida(linha):
    return len(linha) <= 100 and bool(PADRAO.match(linha))


def main(argv):
    if argv and argv[0].endswith("COMMIT_EDITMSG"):
        linhas = [open(argv[0], encoding="utf-8").readline().strip()]
    else:
        faixa = argv[0] if argv else "HEAD"
        linhas = subprocess.run(["git", "log", "--format=%s", faixa], capture_output=True, text=True, check=True).stdout.splitlines()
    ruins = [x for x in linhas if not valida(x)]
    for x in ruins:
        print("FORA DO PADRÃO:", x)
    print(f"{len(linhas) - len(ruins)} de {len(linhas)} mensagens no padrão Conventional Commits")
    return 1 if ruins else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
