/**
 * calculator.js — Basic calculator with left-to-right sequential evaluation.
 *
 * Evaluation model (confirmed by customer):
 *   2 + 3 × 4  →  (2+3)×4  =  20   (NOT 14)
 *   Operator precedence (PEMDAS) is intentionally NOT implemented.
 *
 * US coverage: US-01 add, US-02 subtract, US-03 multiply, US-04 divide,
 *              US-05 clear, US-06 decimal, US-07 chained ops,
 *              US-09 keyboard, US-10 responsive (CSS).
 */

(function () {
  'use strict';

  // ── State ──────────────────────────────────────────────────────────────────
  const state = {
    currentValue:        '0',   // number currently being composed
    previousValue:       null,  // left-hand operand for pending op
    pendingOperator:     null,  // '+' | '-' | '*' | '/'
    justPressedOperator: false, // true right after an operator key
    justPressedEquals:   false, // true right after =
  };

  // ── DOM references ─────────────────────────────────────────────────────────
  const currentEl    = document.getElementById('current');
  const expressionEl = document.getElementById('expression');
  const buttonsEl    = document.querySelector('.buttons');

  // ── Core arithmetic ────────────────────────────────────────────────────────
  function calculate(a, op, b) {
    const numA = parseFloat(a);
    const numB = parseFloat(b);
    if (isNaN(numA) || isNaN(numB)) return 'Error';
    switch (op) {
      case '+': return numA + numB;
      case '-': return numA - numB;
      case '*': return numA * numB;
      case '/': return numB === 0 ? 'Error' : numA / numB;
      default:  return numA;
    }
  }

  /** Remove floating-point noise: 0.1+0.2 → "0.3" not "0.30000000000000004" */
  function formatResult(num) {
    if (num === 'Error') return 'Error';
    if (typeof num !== 'number' || isNaN(num) || !isFinite(num)) return 'Error';
    return parseFloat(num.toPrecision(10)).toString();
  }

  // ── Input handlers ─────────────────────────────────────────────────────────
  function handleDigit(digit) {
    if (state.justPressedOperator || state.justPressedEquals) {
      // Begin a fresh number after an operator or equals
      state.currentValue = (digit === '0') ? '0' : digit;
      state.justPressedOperator = false;
      state.justPressedEquals   = false;
    } else {
      if (state.currentValue.length >= 12) return;            // cap display length
      if (state.currentValue === '0' && digit !== '.') {
        state.currentValue = digit;                           // replace leading zero
      } else {
        state.currentValue += digit;
      }
    }
    updateDisplay();
  }

  function handleDecimal() {
    if (state.justPressedOperator || state.justPressedEquals) {
      state.currentValue = '0.';
      state.justPressedOperator = false;
      state.justPressedEquals   = false;
    } else if (!state.currentValue.includes('.')) {
      if (state.currentValue.length >= 12) return;
      state.currentValue += '.';
    }
    updateDisplay();
  }

  function handleOperator(op) {
    // LEFT-TO-RIGHT: if there's already a pending op, evaluate it immediately
    if (state.pendingOperator !== null && !state.justPressedOperator) {
      const result    = calculate(state.previousValue, state.pendingOperator, state.currentValue);
      const formatted = formatResult(result);
      if (formatted === 'Error') { handleError(); return; }
      state.previousValue = formatted;
    } else {
      // No pending op (or user is swapping operator keys) — store current as left operand
      state.previousValue = state.currentValue;
    }
    state.pendingOperator     = op;
    state.justPressedOperator = true;
    state.justPressedEquals   = false;
    updateDisplay();
  }

  function handleEquals() {
    if (state.pendingOperator === null) return;
    const result    = calculate(state.previousValue, state.pendingOperator, state.currentValue);
    const formatted = formatResult(result);
    if (formatted === 'Error') { handleError(); return; }
    state.currentValue        = formatted;
    state.previousValue       = null;
    state.pendingOperator     = null;
    state.justPressedEquals   = true;
    state.justPressedOperator = false;
    updateDisplay();
  }

  function handleClear() {
    state.currentValue        = '0';
    state.previousValue       = null;
    state.pendingOperator     = null;
    state.justPressedOperator = false;
    state.justPressedEquals   = false;
    updateDisplay();
  }

  function handleError() {
    state.currentValue        = 'Error';
    state.previousValue       = null;
    state.pendingOperator     = null;
    state.justPressedOperator = false;
    state.justPressedEquals   = false;
    updateDisplay();
  }

  // ── Display update ─────────────────────────────────────────────────────────
  const OP_SYMBOLS = { '+': '+', '-': '−', '*': '×', '/': '÷' };

  function updateDisplay() {
    currentEl.textContent = state.currentValue;

    expressionEl.textContent = state.pendingOperator
      ? state.previousValue + ' ' + (OP_SYMBOLS[state.pendingOperator] || state.pendingOperator)
      : '';

    // Shrink font for long numbers
    const len = state.currentValue.length;
    currentEl.classList.toggle('medium', len > 8 && len <= 11);
    currentEl.classList.toggle('small',  len > 11);
  }

  // ── Mouse / touch clicks ───────────────────────────────────────────────────
  buttonsEl.addEventListener('click', function (e) {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const action = btn.dataset.action;
    const value  = btn.dataset.value;
    switch (action) {
      case 'digit':    handleDigit(value);    break;
      case 'decimal':  handleDecimal();        break;
      case 'operator': handleOperator(value); break;
      case 'equals':   handleEquals();         break;
      case 'clear':    handleClear();          break;
    }
  });

  // ── Keyboard support (US-09) ───────────────────────────────────────────────
  const KEY_HANDLER = {
    '0': function() { handleDigit('0'); },
    '1': function() { handleDigit('1'); },
    '2': function() { handleDigit('2'); },
    '3': function() { handleDigit('3'); },
    '4': function() { handleDigit('4'); },
    '5': function() { handleDigit('5'); },
    '6': function() { handleDigit('6'); },
    '7': function() { handleDigit('7'); },
    '8': function() { handleDigit('8'); },
    '9': function() { handleDigit('9'); },
    '.': function() { handleDecimal(); },
    '+': function() { handleOperator('+'); },
    '-': function() { handleOperator('-'); },
    '*': function() { handleOperator('*'); },
    '/': function() { handleOperator('/'); },
    'Enter':  function() { handleEquals(); },
    '=':      function() { handleEquals(); },
    'Escape': function() { handleClear(); },
    'c':      function() { handleClear(); },
    'C':      function() { handleClear(); },
  };

  const KEY_SELECTOR = {
    '0': '[data-action="digit"][data-value="0"]',
    '1': '[data-action="digit"][data-value="1"]',
    '2': '[data-action="digit"][data-value="2"]',
    '3': '[data-action="digit"][data-value="3"]',
    '4': '[data-action="digit"][data-value="4"]',
    '5': '[data-action="digit"][data-value="5"]',
    '6': '[data-action="digit"][data-value="6"]',
    '7': '[data-action="digit"][data-value="7"]',
    '8': '[data-action="digit"][data-value="8"]',
    '9': '[data-action="digit"][data-value="9"]',
    '.': '[data-action="decimal"]',
    '+': '[data-action="operator"][data-value="+"]',
    '-': '[data-action="operator"][data-value="-"]',
    '*': '[data-action="operator"][data-value="*"]',
    '/': '[data-action="operator"][data-value="/"]',
    'Enter':  '[data-action="equals"]',
    '=':      '[data-action="equals"]',
    'Escape': '[data-action="clear"]',
    'c':      '[data-action="clear"]',
    'C':      '[data-action="clear"]',
  };

  document.addEventListener('keydown', function (e) {
    var handler = KEY_HANDLER[e.key];
    if (!handler) return;
    // Prevent "/" opening browser quick-find; prevent "Enter" submitting forms
    if (e.key === '/' || e.key === 'Enter') e.preventDefault();
    handler();
    flashButton(KEY_SELECTOR[e.key]);
  });

  /** Briefly highlight the corresponding button on keyboard press */
  function flashButton(selector) {
    if (!selector) return;
    var btn = document.querySelector(selector);
    if (!btn) return;
    btn.classList.add('active');
    setTimeout(function () { btn.classList.remove('active'); }, 150);
  }

  // ── Bootstrap ──────────────────────────────────────────────────────────────
  updateDisplay();

})();