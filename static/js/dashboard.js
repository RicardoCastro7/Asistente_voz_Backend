// ====== NAV LATERAL (cambiar secciones) ======
    const sidebarItems = document.querySelectorAll('.sidebar-item:not(.disabled)');
    const sections = document.querySelectorAll('.section');

    sidebarItems.forEach(btn => {
      btn.addEventListener('click', () => {
        const target = btn.getAttribute('data-section');
        if (!target) return;

        // marcar activo en menú
        sidebarItems.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        // mostrar sección correspondiente
        sections.forEach(sec => {
          if (sec.id === 'section-' + target) {
            sec.style.display = 'block';
          } else {
            sec.style.display = 'none';
          }
        });
      });
    });

    // mostrar solo la sección marcada con .active al inicio
    sections.forEach(sec => {
      if (sec.classList.contains('active')) {
        sec.style.display = 'block';
      } else {
        sec.style.display = 'none';
      }
    });

    // ====== TU LÓGICA DE SUBIDA / ELIMINACIÓN ======
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('fileInput');
    const btnSelect = document.getElementById('btnSelect');
    const btnRebuild = document.getElementById('btnRebuild'); // por si lo usas
    const fileList = document.getElementById('fileList');     // <ul id="fileList">...</ul>

    if (btnSelect && fileInput) {
      btnSelect.addEventListener('click', () => fileInput.click());

      fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
          uploadFile(e.target.files[0]);
        }
      });
    }

    if (dropzone) {
      dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
      });
      dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
      dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        const file = e.dataTransfer.files[0];
        if (file) uploadFile(file);
      });
    }

    function uploadFile(file) {
      const formData = new FormData();
      formData.append('file', file);

      fetch('/upload', {
        method: 'POST',
        body: formData
      })
        .then(r => r.json())
        .then(data => {
          if (data.ok) {
            addFileToList(data.filename);
          } else {
            alert(data.msg || 'Error al subir');
          }
        })
        .catch(err => {
          console.error(err);
          alert('Error de red');
        });
    }

    // conectar botones eliminar ya existentes
    document.querySelectorAll('.btn-delete').forEach(btn => {
      btn.addEventListener('click', handleDelete);
    });

    function handleDelete(e) {
      const btn = e.target;
      const name = btn.dataset.name;
      if (!confirm('¿Eliminar "' + name + '"?')) return;

      fetch('/delete/' + encodeURIComponent(name), {
        method: 'DELETE'
      })
        .then(r => r.json())
        .then(data => {
          if (data.ok) {
            const li = btn.closest('li');
            li.style.transition = "opacity 0.25s ease, transform 0.25s ease";
            li.style.opacity = "0";
            li.style.transform = "translateX(-6px)";
            setTimeout(() => li.remove(), 250);
          } else {
            alert(data.msg || 'No se pudo eliminar');
          }
        });
    }

    function addFileToList(filename) {
      if (!fileList) return;

      const li = document.createElement('li');
      li.dataset.name = filename;
      li.innerHTML = `
        <span class="file-icon">📄</span>
        <a href="/files/${encodeURIComponent(filename)}" target="_blank">${filename}</a>
        <button class="btn-delete" data-name="${filename}">Eliminar</button>
      `;

      fileList.appendChild(li);

      li.style.opacity = "0";
      li.style.transform = "translateY(-4px)";
      setTimeout(() => {
        li.style.transition = "opacity 0.25s ease, transform 0.25s ease";
        li.style.opacity = "1";
        li.style.transform = "translateY(0)";
      }, 30);

      li.querySelector('.btn-delete').addEventListener('click', handleDelete);
    }

    if (btnRebuild) {
      btnRebuild.addEventListener('click', () => {
        fetch('/rebuild', { method: 'POST' })
          .then(r => r.json())
          .then(data => {
            if (data.ok) alert('Reprocesado correctamente.');
          });
      });
    }


    // Confirmar eliminación de prompt
    document.querySelectorAll('.form-delete-prompt').forEach(form => {
      form.addEventListener('submit', (e) => {
        if (!confirm('¿Seguro que deseas eliminar este prompt?')) {
          e.preventDefault();
        }
      });
    });

    // Confirmar rechazo de usuario
    document.querySelectorAll('.form-reject-user').forEach(form => {
      form.addEventListener('submit', (e) => {
        if (!confirm('¿Seguro que deseas rechazar / eliminar esta cuenta?')) {
          e.preventDefault();
        }
      });
    });

    function showToast(message, type = "ok") {
      if (!toast) return;
      toast.textContent = message;
      toast.className = "toast " + type + " show";
      setTimeout(() => {
        toast.classList.remove("show");
      }, 2500);
    }
    // ====== CHAT ASISTENTE DE VOZ (usa /rag) ======
    const chatInput = document.getElementById('chatInput');
    const chatSendBtn = document.getElementById('chatSendBtn');
    const chatMessages = document.getElementById('chatMessages');

    function appendMessage(text, from = 'user') {
      const msg = document.createElement('div');
      msg.classList.add('msg');
      msg.classList.add(from === 'user' ? 'msg-user' : 'msg-bot');

      const avatar = document.createElement('div');
      avatar.classList.add('msg-avatar');
      avatar.textContent = from === 'user' ? '🙋‍♂️' : '🤖';

      const bubble = document.createElement('div');
      bubble.classList.add('msg-bubble');
      bubble.innerHTML = `<p>${text}</p>`;

      msg.appendChild(avatar);
      msg.appendChild(bubble);

      chatMessages.appendChild(msg);
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function appendTyping() {
      const msg = document.createElement('div');
      msg.classList.add('msg', 'msg-bot');
      msg.id = 'typing-indicator';

      const avatar = document.createElement('div');
      avatar.classList.add('msg-avatar');
      avatar.textContent = '🤖';

      const bubble = document.createElement('div');
      bubble.classList.add('msg-bubble');
      bubble.innerHTML = `
        <div class="typing-dots">
          <span></span><span></span><span></span>
        </div>
      `;

      msg.appendChild(avatar);
      msg.appendChild(bubble);
      chatMessages.appendChild(msg);
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function removeTyping() {
      const t = document.getElementById('typing-indicator');
      if (t) t.remove();
    }

    async function sendMessage() {
      const text = (chatInput.value || '').trim();
      if (!text) return;

      appendMessage(text, 'user');
      chatInput.value = '';

      appendTyping();

      try {
        const resp = await fetch('/rag', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pregunta: text })
        });

        const data = await resp.json();
        removeTyping();

        if (data.respuesta) {
          appendMessage(data.respuesta, 'bot');
        } else if (data.error) {
          appendMessage('Ocurrió un error: ' + data.error, 'bot');
        } else {
          appendMessage('No se recibió respuesta del servidor.', 'bot');
        }
      } catch (err) {
        console.error(err);
        removeTyping();
        appendMessage('Error de red al contactar con el servidor.', 'bot');
      }
    }

    if (chatSendBtn && chatInput) {
      chatSendBtn.addEventListener('click', sendMessage);
      chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          sendMessage();
        }
      });
    }
    
