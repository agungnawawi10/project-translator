document.addEventListener('DOMContentLoaded', function() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const resultSection = document.getElementById('result-section');
    const videoPlayer = document.getElementById('video-player');
    const videoSource = document.getElementById('video-source');
    const loading = document.getElementById('loading');

    dropZone.addEventListener('click', () => fileInput.click());

    fileInput.addEventListener('change', function() {
        if (this.files && this.files[0]) {
            uploadAndProcessVideo(this.files[0]);
        }
    });

    dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('drag-over'); });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        if (e.dataTransfer.files.length > 0) {
            const file = e.dataTransfer.files[0];
            if (file.type.startsWith('video/')) {
                fileInput.files = e.dataTransfer.files;
                uploadAndProcessVideo(file);
            } else {
                alert('Mohon masukkan file format video!');
            }
        }
    });

    function uploadAndProcessVideo(file) {
        loading.classList.remove('hidden');
        resultSection.classList.add('hidden');

        const formData = new FormData();
        formData.append('video', file);

        fetch('/translate_video', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            loading.classList.add('hidden');
            
            if (data.error) {
                alert(data.error);
            } else {
                resultSection.classList.remove('hidden');
                // Masukkan path video hasil olahan Python ke pemutar HTML
                videoSource.src = data.video_url;
                videoPlayer.load(); // Reload resource video baru
                videoPlayer.play(); // Putar otomatis
            }
        })
        .catch(error => {
            loading.classList.add('hidden');
            alert("Gagal memproses video. Pastikan ukuran video tidak terlalu besar.");
            console.error(error);
        });
    }
});