def pode_arrepender(recebimento, hoje):
    dias = (hoje - recebimento).days
    if dias < 0:
        raise ValueError("data de recebimento no futuro")
    return dias <= 7
