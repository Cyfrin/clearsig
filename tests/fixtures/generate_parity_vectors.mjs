// Generate parity vectors using viem (the canonical JS EIP-712 + Safe hash implementation).
// Output is written to tests/fixtures/parity_vectors.json and is checked into source.
//
// Regenerate when you add a new vector:
//   cd /Users/patrick/code/chain-tools && node /Users/patrick/code/erc7730-converter/tests/fixtures/generate_parity_vectors.mjs
//
// Run from the chain-tools repo so viem resolves; the output path is absolute.

import { writeFileSync } from 'node:fs';
import {
  keccak256,
  toBytes,
  numberToHex,
  concat,
  toHex,
  hashTypedData,
  hashDomain,
  hashStruct,
} from 'viem';

const OUT = '/Users/patrick/code/erc7730-converter/tests/fixtures/parity_vectors.json';

// ---------- calldata digest (ERC-8213) ----------

function calldataDigest(hex) {
  const bytes = toBytes(hex);
  const lenWord = numberToHex(bytes.length, { size: 32 });
  return keccak256(concat([toBytes(lenWord), bytes]));
}

const calldataCases = [
  { label: 'empty', input: '0x' },
  { label: 'one byte', input: '0xff' },
  { label: 'bare selector', input: '0x095ea7b3' },
  {
    label: 'ERC-20 transfer',
    input:
      '0xa9059cbb' +
      '0000000000000000000000004675c7e5baafbffbca748158becba61ef3b0a263' +
      '0000000000000000000000000000000000000000000000000de0b6b3a7640000',
  },
  // varied lengths
  { label: '32 random bytes', input: '0x' + 'ab'.repeat(32) },
  { label: '128 random bytes', input: '0x' + 'cd'.repeat(128) },
  { label: '513 bytes (odd)', input: '0x' + 'ef'.repeat(513) },
];

const calldataVectors = calldataCases.map((c) => ({
  label: c.label,
  input: c.input,
  digest: calldataDigest(c.input),
}));

// ---------- EIP-712 ----------

function eip712Hashes(doc) {
  return {
    domainHash: hashDomain({ domain: doc.domain, types: doc.types }),
    messageHash: hashStruct({
      data: doc.message,
      types: Object.fromEntries(
        Object.entries(doc.types).filter(([k]) => k !== 'EIP712Domain'),
      ),
      primaryType: doc.primaryType,
    }),
    digest: hashTypedData(doc),
  };
}

const eip712Cases = [
  {
    label: 'EIP-712 spec Mail',
    doc: {
      types: {
        EIP712Domain: [
          { name: 'name', type: 'string' },
          { name: 'version', type: 'string' },
          { name: 'chainId', type: 'uint256' },
          { name: 'verifyingContract', type: 'address' },
        ],
        Person: [
          { name: 'name', type: 'string' },
          { name: 'wallet', type: 'address' },
        ],
        Mail: [
          { name: 'from', type: 'Person' },
          { name: 'to', type: 'Person' },
          { name: 'contents', type: 'string' },
        ],
      },
      primaryType: 'Mail',
      domain: {
        name: 'Ether Mail',
        version: '1',
        chainId: 1,
        verifyingContract: '0xCcCCccccCCCCcCCCCCCcCcCccCcCCCcCcccccccC',
      },
      message: {
        from: { name: 'Cow', wallet: '0xCD2a3d9F938E13CD947Ec05AbC7FE734Df8DD826' },
        to: { name: 'Bob', wallet: '0xbBbBBBBbbBBBbbbBbbBbbbbBBbBbbbbBbBbbBBbB' },
        contents: 'Hello, Bob!',
      },
    },
  },
  {
    // Tests: nested struct, JSON-string uint256 coercion, sparse domain (no `version`)
    label: 'Permit2 PermitTransferFrom',
    doc: {
      types: {
        EIP712Domain: [
          { name: 'name', type: 'string' },
          { name: 'chainId', type: 'uint256' },
          { name: 'verifyingContract', type: 'address' },
        ],
        PermitTransferFrom: [
          { name: 'permitted', type: 'TokenPermissions' },
          { name: 'spender', type: 'address' },
          { name: 'nonce', type: 'uint256' },
          { name: 'deadline', type: 'uint256' },
        ],
        TokenPermissions: [
          { name: 'token', type: 'address' },
          { name: 'amount', type: 'uint256' },
        ],
      },
      primaryType: 'PermitTransferFrom',
      domain: {
        name: 'Permit2',
        chainId: 1,
        verifyingContract: '0x000000000022D473030F116dDEE9F6B43aC78BA3',
      },
      message: {
        permitted: {
          token: '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48',
          amount: '1000000000',
        },
        spender: '0xE592427A0AEce92De3Edee1F18E0157C05861564',
        nonce: '0',
        deadline: '1893456000',
      },
    },
  },
  {
    // Tests: bytes32 atomic, bool, dynamic bytes
    label: 'mixed atomic types',
    doc: {
      types: {
        EIP712Domain: [
          { name: 'name', type: 'string' },
          { name: 'chainId', type: 'uint256' },
          { name: 'verifyingContract', type: 'address' },
        ],
        Mixed: [
          { name: 'flag', type: 'bool' },
          { name: 'salt', type: 'bytes32' },
          { name: 'payload', type: 'bytes' },
          { name: 'count', type: 'uint8' },
          { name: 'signed', type: 'int256' },
        ],
      },
      primaryType: 'Mixed',
      domain: { name: 'Mixed', chainId: 1, verifyingContract: '0x' + '00'.repeat(20) },
      message: {
        flag: true,
        salt: '0x' + 'a1'.repeat(32),
        payload: '0xdeadbeefcafebabe',
        count: 255,
        signed: -42,
      },
    },
  },
  {
    // Tests: dynamic array of atomic
    label: 'array of uint256',
    doc: {
      types: {
        EIP712Domain: [{ name: 'name', type: 'string' }],
        Bag: [{ name: 'items', type: 'uint256[]' }],
      },
      primaryType: 'Bag',
      domain: { name: 'Bag' },
      message: { items: ['1', '2', '3', '1000000000000000000'] },
    },
  },
  {
    // Tests: fixed-size array of address
    label: 'fixed-size address array',
    doc: {
      types: {
        EIP712Domain: [{ name: 'name', type: 'string' }],
        Trio: [{ name: 'addrs', type: 'address[3]' }],
      },
      primaryType: 'Trio',
      domain: { name: 'Trio' },
      message: {
        addrs: [
          '0xCD2a3d9F938E13CD947Ec05AbC7FE734Df8DD826',
          '0xbBbBBBBbbBBBbbbBbbBbbbbBBbBbbbbBbBbbBBbB',
          '0x' + '01'.repeat(20),
        ],
      },
    },
  },
  {
    // Tests: array of struct (a common Permit2 pattern)
    label: 'array of struct',
    doc: {
      types: {
        EIP712Domain: [{ name: 'name', type: 'string' }],
        Basket: [{ name: 'items', type: 'Item[]' }],
        Item: [
          { name: 'id', type: 'uint256' },
          { name: 'owner', type: 'address' },
        ],
      },
      primaryType: 'Basket',
      domain: { name: 'Basket' },
      message: {
        items: [
          { id: '1', owner: '0xCD2a3d9F938E13CD947Ec05AbC7FE734Df8DD826' },
          { id: '2', owner: '0xbBbBBBBbbBBBbbbBbbBbbbbBBbBbbbbBbBbbBBbB' },
        ],
      },
    },
  },
  {
    // Tests: multi-dim array
    label: '2D uint256 matrix',
    doc: {
      types: {
        EIP712Domain: [{ name: 'name', type: 'string' }],
        Matrix: [{ name: 'rows', type: 'uint256[][]' }],
      },
      primaryType: 'Matrix',
      domain: { name: 'Matrix' },
      message: {
        rows: [
          ['1', '2'],
          ['3', '4'],
          ['5', '6'],
        ],
      },
    },
  },
];

const eip712Vectors = eip712Cases.map((c) => ({
  label: c.label,
  doc: c.doc,
  ...eip712Hashes(c.doc),
}));

// ---------- write fixtures ----------

const output = {
  generator: 'viem',
  generatedAt: new Date().toISOString(),
  calldataDigest: calldataVectors,
  eip712: eip712Vectors,
};

writeFileSync(OUT, JSON.stringify(output, null, 2) + '\n');
console.log(`Wrote ${calldataVectors.length} calldata + ${eip712Vectors.length} EIP-712 vectors to ${OUT}`);
