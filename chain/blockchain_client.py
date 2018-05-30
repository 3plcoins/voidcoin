import json
import hashlib

from uuid import uuid4
from time import time
from collections import OrderedDict
from urllib.parse import urlparse

import requests

import binascii
import Crypto
import Crypto.Random
from Crypto.Hash import SHA
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5

MINING_DIFFICULTY = 2
MINING_SENDER = 'VOIDCOIN'
MINING_REWARD = 0.25
COINBASE = 1000.00

class Transaction:
    def __init__(self, sender_address, sender_private_key, recipient_address, amount):
        self.sender_address = sender_address
        self.sender_private_key = sender_private_key
        self.recipient_address = recipient_address
        self.timestamp = time()
        self.amount = amount

    def __getattr__(self, attr):
        return self.data[attr]

    def to_dict(self):
        return OrderedDict(
            {'sender_address': self.sender_address,
            'recipient_address': self.recipient_address,
            'amount' : self.amount})

    def sign_transaction(self):
        """Sign the transaction with sender's private key"""
        private_key = RSA.importKey(binascii.unhexlify(self.sender_private_key))
        signer = PKCS1_v1_5.new(private_key)
        h = SHA.new(str(self.to_dict()).encode('utf-8'))
        return binascii.hexlify(signer.sign(h)).decode('ascii')

class Blockchain:
    def __init__(self):
        self.transactions = []
        self.chain = []
        # self.nodes = set()
        self.nodes = OrderedDict()
        # Random number to use as node id
        self.node_id = str(uuid4()).replace('-', '')
        # Genesis block
        self.create_block_and_add_to_chain(0, '00')

    def register_node(self, node_url):
        """
        Add new node to the nodes dictionary

        Parameters
        -----------
        node_url : str
            Node url e.g http://127.0.0.1
        """

        parsed_url = urlparse(node_url)
        if parsed_url.netloc:
            self.nodes[parsed_url.netloc] = time()
        elif parsed_url.path:
            self.nodes[parsed_url.path] = time()
        else:
            raise ValueError("Invalid url")

    def verify_transaction_signature(self, sender_address, signature, transaction):
        """
        Verifies that provided signature is actually signed by sender_address (public key)

        Parameters
        -----------

        Returns
        ---------
        bool
            True if transaction is valid (signature is signed by sender_address). False otherwise.
        """
        public_key = RSA.importKey(binascii.unhexlify(sender_address))
        verifier = PKCS1_v1_5.new(public_key)
        h = SHA.new(str(transaction)).encode('utf-8')
        return verifier.verify(h, binascii.unhexlify(signature))

    def add_transaction_to_current_array(self, sender_address, recipient_address, amount, signature):
        """
        Add transaction to the transaction array if it can be verified
        """
        transaction = OrderedDict({'sender_address': sender_address,
                                    'recipient_address': recipient_address,
                                    'amount': amount})
        # Reward miner
        if sender_address == MINING_SENDER:
            self.transactions.append(transaction)
            return len(self.chain) + 1

        # Manages transactions from wallet to another wallet
        else:
            verify = self.verify_transaction_signature(sender_address, signature, transaction)
            if verify:
                self.transactions.append(transaction)
                return len(self.chain) + 1
            else:
                return False

    def create_block_and_add_to_chain(self, nonce, previous_hash):
        """
        Add a block of transactions to the chain
        """
        block = {'block_number': len(self.chain) + 1,
                'timestamp': time(),
                'transactions': self.transactions,
                'nonce': nonce,
                'previous_hash': previous_hash}

        # Reset the current list of transactions
        self.transactions = []

        self.chain.append(block)
        return block

    @staticmethod
    def hash(block):
        """
        Create SHA-256 hash of a block
        """
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def proof_of_work(self):
        """
        Proof of work algorithm
        """
        last_hash = self.hash(self.last_block)
        nonce = 0
        while self.valid_proof(self.transactions, last_hash, nonce) is False:
            nonce += 1
        return nonce

    def valid_proof(self, transactions, last_hash, nonce, difficulty=MINING_DIFFICULTY):
        """
        Check whether hash satisfies mining conditions.

        Parameters
        -----------
        transactions : list
            Current transactions
        last_hash : str
            Last hash value
        difficulty : int
            Represents how hard our mining algorithm should be

        Returns
        --------
        bool :
            True if mining condition is satisfied. False otherwise
        """
        guess = (str(transactions) + str(last_hash) + str(nonce)).encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:difficulty] == '0'*difficulty

    def valid_chain(self, chain):
        """
        Check whether blockchain is valid

        Parameters
        -----------
        chain : Blockchain
            A blockchain instance

        Returns
        ---------
        bool :
            Return True if valid. False otherwise.
        """
        last_block = chain[0]
        current_index = 1

        while current_index < len(chain):
            block = chain[current_index]

            # Check that the hash of the block is correct
            if block['previous_hash'] != self.hash(last_block):
                return False

            # Check that the Proof of Work is correct
            # Delete the reward transaction
            transactions = block['transactions'][:-1]

            # Need to make sure that the dictionary is ordered. Otherwise we'll get a different hash
            transaction_elements = ['sender_address', 'recipient_address', 'value']
            transactions = [OrderedDict((k, transaction[k]) for k in transaction_elements) for transaction in transactions]

            if not self.valid_proof(transactions, block['previous_hash'], block['nonce'], MINING_DIFFICULTY):
                return False

            last_block = block
            current_index += 1

        return True

    def resolve_conflicts(self):
        """
        Resolve conflicts between blockchain's nodes
        by replacing our chain with the longest one in the network.
        """
        neighbours = [value for key, value in self.nodes.items()]
        new_chain = None

        # We're only looking for chains longer than ours
        max_length = len(self.chain)

        # Grab and verify the chains from all the nodes in our network
        for node in neighbours:
            print('http://' + node + '/chain')
            response = requests.get('http://' + node + '/chain')

            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']

                # Check if the length is longer and the chain is valid
                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain

        # Replace our chain if we discovered a new, valid chain longer than ours
        if new_chain:
            self.chain = new_chain
            return True
        return False

    def last_block(self):
        return self.chain[-1]
