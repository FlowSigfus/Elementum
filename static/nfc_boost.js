// static/nfc_boost.js
document.getElementById('boostButton').addEventListener('click', async () => {
    if (!('NDEFReader' in window)) {
        alert('Web NFC не поддерживается. Используйте Chrome на Android.');
        return;
    }
    try {
        const reader = new NDEFReader();
        await reader.scan();
        reader.onreading = async (event) => {
            const tagId = event.serialNumber;
            const response = await fetch('/api/nfc_boost', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tag_id: tagId })
            });
            const data = await response.json();
            if (data.success) {
                alert(data.message);
                location.reload();
            } else {
                alert('Ошибка: ' + data.message);
            }
            reader.stop();
        };
    } catch (error) {
        alert('Ошибка NFC: ' + error.message);
    }
});