// static/nfc.js
document.addEventListener('DOMContentLoaded', () => {
    const scanButton = document.getElementById('scanButton');
    const resultParagraph = document.getElementById('result');

    scanButton.addEventListener('click', async () => {
        if (!('NDEFReader' in window)) {
            resultParagraph.textContent = 'Web NFC не поддерживается вашим браузером.';
            return;
        }

        resultParagraph.textContent = 'Поднесите NFC-метку...';
        scanButton.disabled = true;

        try {
            const reader = new NDEFReader();

            reader.onreading = async (event) => {
                // Извлекаем текстовые данные с метки (nfc_hash)
                let tagData = null;
                for (const record of event.message.records) {
                    if (record.recordType === "text") {
                        const decoder = new TextDecoder(record.encoding);
                        tagData = decoder.decode(record.data);
                        break;
                    } else if (record.recordType === "url") {
                        const decoder = new TextDecoder();
                        tagData = decoder.decode(record.data);
                        break;
                    }
                }

                if (!tagData) {
                    resultParagraph.innerHTML = '<strong style="color: red;">❌ Не удалось прочитать данные с метки.</strong>';
                    scanButton.disabled = false;
                    reader.stop();
                    return;
                }

                // Отправляем данные на сервер
                try {
                    const response = await fetch('/api/nfc_scan', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ tag_id: tagData })
                    });
                    const data = await response.json();
                    if (data.success) {
                        resultParagraph.innerHTML = `<strong style="color: green;">✅ ${data.message}</strong>`;
                    } else {
                        resultParagraph.innerHTML = `<strong style="color: red;">❌ ${data.message}</strong>`;
                    }
                } catch (fetchError) {
                    resultParagraph.innerHTML = '<strong style="color: red;">❌ Ошибка связи с сервером.</strong>';
                } finally {
                    reader.stop();
                    scanButton.disabled = false;
                }
            };

            reader.onerror = (error) => {
                resultParagraph.textContent = 'Ошибка NFC: ' + error.message;
                scanButton.disabled = false;
            };

            await reader.scan();
        } catch (error) {
            resultParagraph.textContent = 'Ошибка запуска сканера: ' + error.message;
            scanButton.disabled = false;
        }
    });
});
