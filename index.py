from flask import Flask, render_template
from flask import request
import time
import logging
import re
import subprocess
import sqlite3

app = Flask(__name__)
logger = logging.getLogger('btczfaucet')
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler('log.txt')
fh.setLevel(logging.DEBUG)
logger.addHandler(fh)

alphabet = '123456789abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ'
base_count = len(alphabet)
DONATION = 0.15

def encode(num):
    """ Returns num in a base58-encoded string """
    encode = ''

    if (num < 0):
        return ''

    while (num >= base_count):
        mod = num % base_count
        encode = alphabet[mod] + encode
        num = num / base_count

    if (num):
        encode = alphabet[num] + encode

    return encode

def decode(s):
    """ Decodes the base58-encoded string s into an integer """
    decoded = 0
    multi = 1
    s = s[::-1]
    for char in s:
        decoded += multi * alphabet.index(char)
        multi = multi * base_count

    return decoded

@app.route('/')
def index():
    db = sqlite3.connect('db/faucet_db')
    cursor = db.cursor()
    cursor.execute('SELECT amount FROM total')
    faucet_total = cursor.fetchone()
    if faucet_total is None:
        faucet_total = '0.0'
    else:
        faucet_total = faucet_total[0]
    return render_template('index.html', donation=DONATION, faucet_total=faucet_total)

@app.route('/faucet', methods=['POST'])
def post():

    # sanitize wallet address
    insecure_wallet_address = request.form.get("wallet_address")
    try:
        decoded_wallet_address = decode(insecure_wallet_address)
        encoded_wallet_address = encode(decoded_wallet_address)

        if insecure_wallet_address != encoded_wallet_address:
            raise ValueError
    except ValueError:
        return render_template('faucet.html', message='Invalid wallet address')
    
    if len(encoded_wallet_address) != 35:
        return render_template('faucet.html', message='Invalid wallet address')

    if encoded_wallet_address[:2] != 't1':
        return render_template('faucet.html', message='Invalid wallet address')
    
    verified_wallet_address = encoded_wallet_address
    
    # sanitize IP address
    insecure_ip_address = request.remote_addr
    if not [0<=int(x)<256 for x in re.split('\.',re.match(r'^\d+\.\d+\.\d+\.\d+$',insecure_ip_address).group(0))].count(True)==4:
        logger.error("Invalid ip: %s" % insecure_ip_address)
        return render_template('faucet.html', message='Invalid IP address')
    verified_ip_address = insecure_ip_address

    # Make sure Faucet wallet has enough for donation
    command = ['/home/ubuntu/bitcoinz/src/zcash-cli',
               'getbalance']

    try:
        p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, error = p.communicate()
    except:
        return render_template('faucet.html', message='Error running zcash-cli')

    logger.info("getbalance - Output: %s, Error:%s" % (output.rstrip(), error))

    wallet_total = float(output)
    if wallet_total <= 0.002:
        return render_template('faucet.html', message='No btcz left in wallet')
    
    # Check IP address within 24hour
    db = sqlite3.connect('db/faucet_db')
    cursor = db.cursor()
    cursor.execute('SELECT time FROM donations WHERE wallet = ? OR ip = ?', (verified_wallet_address, verified_ip_address))
    last_donation_time = cursor.fetchone()
    current_unix_time = time.time()
    if last_donation_time is not None and last_donation_time[0] + 86400 > current_unix_time:
        logger.error("Same IP: %s, or wallet: %s in less than 24 hours" % (verified_ip_address, verified_wallet_address))
        return render_template('faucet.html', message='Cannot request btcz more than once every 24 hours')        
            
    # At this point, all the checks have been passed. Transfer the btcz to the wallet address.
    command = ['/home/ubuntu/bitcoinz/src/zcash-cli',
                              'sendtoaddress',
                              verified_wallet_address,
                              '0.002']

    try:
        p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, error = p.communicate()
    except:
        db.close()
        logger.error("Error transfering to wallet")
        return render_template('faucet.html', message='Error transfering btcz to wallet address')

    db.execute("INSERT INTO donations (ip, wallet, donation, time) VALUES (?,?,?,?)",
              (verified_ip_address, verified_wallet_address, DONATION, current_unix_time))
    db.commit()

    db.execute("UPDATE total SET amount = amount + ? WHERE amount > -1;", [DONATION])
    db.commit()
    
    logger.info("Donated: %s to %s for %s" % (DONATION, verified_wallet_address, verified_ip_address))
    message = "Follow this transaction: https://sk.bitcoinz.global/tx/%s" % output.strip()
    db.close()

    return render_template('faucet.html', message=message)

if __name__ == '__main__':
    app.run(host='0.0.0.0')
