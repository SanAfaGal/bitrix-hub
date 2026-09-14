  var form = document.getElementById('authorization-form');
  var status = document.getElementById('form-status');
  var submitButton = document.getElementById('submit-button');

  // Mensajes propios de Alberto Álvarez en vez de los globos genéricos del
  // navegador ("Please fill out this field") — el <form> lleva `novalidate`
  // y esta validación reemplaza por completo a la nativa. Los de campos
  // obligatorios van junto al campo (`.field__error`), no en un mensaje
  // general abajo del formulario — así la persona ve de una cuál dato falta.
  function showFormError(message) {
    status.className = 'form-status--error';
    status.textContent = message;
  }
  function clearFormError() {
    status.className = '';
    status.textContent = '';
  }
