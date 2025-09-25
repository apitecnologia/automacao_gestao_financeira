import os
import calendar
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
from datetime import date, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import io

app = Flask(__name__)

# --- CORREÇÕES APLICADAS ---
# Carrega a configuração do banco de dados e a chave secreta das variáveis de ambiente da Render
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), nullable=False, unique=True)
    password = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    telefone = db.Column(db.String(20), nullable=True)
    pedidos = db.relationship('Pedido', backref='cliente', lazy=True, cascade="all, delete-orphan")

class Pedido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero_pedido = db.Column(db.String(50), nullable=False, unique=True)
    valor_total = db.Column(db.Float, nullable=False)
    forma_pagamento = db.Column(db.String(50), nullable=False)
    num_parcelas = db.Column(db.Integer)
    data_lancamento = db.Column(db.Date, nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    parcelas = db.relationship('Parcela', backref='pedido', lazy=True, cascade="all, delete-orphan")

class Parcela(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    valor = db.Column(db.Float, nullable=False)
    data_vencimento = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(50), nullable=False, default='Pendente')
    parcela_num = db.Column(db.Integer, nullable=False)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedido.id'), nullable=False)

@app.context_processor
def inject_user():
    return dict(current_user=current_user)

def add_months(sourcedate, months):
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user:
            if check_password_hash(user.password, request.form['password']):
                login_user(user)
                flash('Login realizado com sucesso!', 'success')
                return redirect(url_for('index'))
        flash('Usuário ou senha inválidos. Tente novamente.', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if User.query.count() > 0 and not current_user.is_authenticated:
        flash('Registro de novos usuários desabilitado. Por favor, faça login.', 'info')
        return redirect(url_for('login'))
    if request.method == 'POST':
        hashed_password = generate_password_hash(request.form['password'], method='scrypt')
        is_admin = (User.query.count() == 0)
        new_user = User(username=request.form['username'], password=hashed_password, is_admin=is_admin)
        db.session.add(new_user)
        db.session.commit()
        flash('Conta criada com sucesso!', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/clientes', methods=['GET', 'POST'])
@login_required
def clientes():
    if request.method == 'POST':
        nome_cliente = request.form['nome']
        telefone_cliente = request.form['telefone']
        novo_cliente = Cliente(nome=nome_cliente, telefone=telefone_cliente)
        db.session.add(novo_cliente)
        db.session.commit()
        return redirect(url_for('clientes'))
    
    todos_clientes = Cliente.query.all()
    return render_template('clientes.html', clientes=todos_clientes)

@app.route('/excluir_cliente/<int:id>')
@login_required
def excluir_cliente(id):
    cliente_a_excluir = Cliente.query.get_or_404(id)
    db.session.delete(cliente_a_excluir)
    db.session.commit()
    return redirect(url_for('clientes'))

@app.route('/pedidos', methods=['GET', 'POST'])
@login_required
def pedidos():
    if request.method == 'POST':
        numero = request.form['numero_pedido']
        valor = float(request.form['valor'])
        forma_pgto = request.form['forma_pagamento']
        cliente_nome = request.form['cliente_nome']
        data_vencimento = date.fromisoformat(request.form['data_vencimento'])

        cliente = Cliente.query.filter_by(nome=cliente_nome).first()
        if not cliente:
            cliente = Cliente(nome=cliente_nome)
            db.session.add(cliente)
            db.session.commit()
        
        num_parcelas = request.form.get('num_parcelas')
        if num_parcelas:
            num_parcelas = int(num_parcelas)
        else:
            num_parcelas = 1

        novo_pedido = Pedido(
            numero_pedido=numero,
            valor_total=valor,
            forma_pagamento=forma_pgto,
            num_parcelas=num_parcelas,
            data_lancamento=date.today(),
            cliente_id=cliente.id
        )
        db.session.add(novo_pedido)
        db.session.flush()

        parcela_valor = valor / num_parcelas
        for i in range(num_parcelas):
            data_parcela = add_months(data_vencimento, i)
            nova_parcela = Parcela(
                valor=parcela_valor,
                data_vencimento=data_parcela,
                parcela_num=i + 1,
                pedido_id=novo_pedido.id,
                status='Pendente'
            )
            db.session.add(nova_parcela)

        db.session.commit()
        return redirect(url_for('pedidos'))

    todos_pedidos = Pedido.query.all()
    return render_template('pedidos.html', pedidos=todos_pedidos)

@app.route('/dar_baixa_parcela/<int:id>', methods=['POST'])
@login_required
def dar_baixa_parcela(id):
    parcela = Parcela.query.get_or_404(id)
    parcela.status = 'Baixado'
    db.session.commit()
    # Redireciona de volta para a página de onde o usuário veio
    return redirect(request.referrer or url_for('pedidos'))

@app.route('/excluir_pedido/<int:id>')
@login_required
def excluir_pedido(id):
    pedido_a_excluir = Pedido.query.get_or_404(id)
    db.session.delete(pedido_a_excluir)
    db.session.commit()
    return redirect(url_for('pedidos'))

@app.route('/gestao_financeira', methods=['GET'])
@login_required
def gestao_financeira():
    mes_str = request.args.get('mes')
    ano_str = request.args.get('ano')

    if mes_str and ano_str:
        mes = int(mes_str)
        ano = int(ano_str)
    else:
        hoje = date.today()
        mes = hoje.month
        ano = hoje.year

    parcelas = Parcela.query.order_by(Parcela.data_vencimento).all()
    fluxo_caixa_mensal = {}

    for parcela in parcelas:
        chave_mes = f"{parcela.data_vencimento.year}-{parcela.data_vencimento.month:02d}"
        if chave_mes not in fluxo_caixa_mensal:
            fluxo_caixa_mensal[chave_mes] = {'total_receber': 0, 'total_baixado': 0, 'parcelas': []}
        
        fluxo_caixa_mensal[chave_mes]['parcelas'].append({
            'id': parcela.id,
            'numero_pedido': parcela.pedido.numero_pedido,
            'cliente_nome': parcela.pedido.cliente.nome,
            'valor': parcela.valor,
            'parcelas': f'{parcela.parcela_num}/{parcela.pedido.num_parcelas}',
            'data_vencimento': parcela.data_vencimento,
            'status': parcela.status
        })

        if parcela.status == 'Baixado':
            fluxo_caixa_mensal[chave_mes]['total_baixado'] += parcela.valor
        else:
            fluxo_caixa_mensal[chave_mes]['total_receber'] += parcela.valor

    fluxo_mes_selecionado = fluxo_caixa_mensal.get(f"{ano}-{mes:02d}", {'total_receber': 0, 'total_baixado': 0, 'parcelas': []})
    
    total_a_receber = fluxo_mes_selecionado['total_receber']
    total_baixado = fluxo_mes_selecionado['total_baixado']
    
    parcelas_do_mes = sorted(fluxo_mes_selecionado['parcelas'], key=lambda p: p['data_vencimento'])
    
    meses_disponiveis = sorted(fluxo_caixa_mensal.keys())

    return render_template(
        'gestao_financeira.html',
        parcelas_do_mes=parcelas_do_mes,
        total_a_receber=total_a_receber,
        total_baixado=total_baixado,
        mes=mes,
        ano=ano,
        meses_disponiveis=meses_disponiveis
    )

@app.route('/exportar_pedidos')
@login_required
def exportar_pedidos():
    parcelas = Parcela.query.all()
    
    dados = [{
        'Numero do Pedido': p.pedido.numero_pedido,
        'Cliente': p.pedido.cliente.nome,
        'Valor da Parcela': p.valor,
        'Forma de Pagamento': p.pedido.forma_pagamento,
        'Numero da Parcela': f'{p.parcela_num}/{p.pedido.num_parcelas}',
        'Data de Vencimento': p.data_vencimento,
        'Status': p.status
    } for p in parcelas]

    df = pd.DataFrame(dados)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Parcelas')
    output.seek(0)

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='relatorio_financeiro.xlsx'
    )

@app.route('/admin_users', methods=['GET'])
@login_required
def admin_users():
    if not current_user.is_admin:
        flash('Acesso negado. Você não tem permissão de administrador.', 'error')
        return redirect(url_for('index'))
    todos_usuarios = User.query.all()
    return render_template('admin_users.html', users=todos_usuarios)

@app.route('/reset_password/<int:user_id>', methods=['POST'])
@login_required
def reset_password(user_id):
    if not current_user.is_admin:
        flash('Acesso negado. Você não tem permissão de administrador.', 'error')
        return redirect(url_for('index'))
    
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash('Não é possível resetar a senha de um administrador.', 'error')
        return redirect(url_for('admin_users'))

    nova_senha = request.form['new_password']
    if not nova_senha:
        flash('A nova senha não pode ser vazia.', 'error')
        return redirect(url_for('admin_users'))

    user.password = generate_password_hash(nova_senha, method='scrypt')
    db.session.commit()
    flash(f'A senha do usuário {user.username} foi redefinida com sucesso!', 'success')
    return redirect(url_for('admin_users'))

# --- AJUSTE PARA IMPLANTAÇÃO ---
# O bloco abaixo garante que as tabelas do banco de dados sejam criadas
# automaticamente quando a aplicação iniciar no servidor do Render.
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)