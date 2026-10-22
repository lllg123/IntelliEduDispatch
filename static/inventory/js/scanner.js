// sherlock-python/static/inventory/js/scanner.js

/**
 * scanner.js
 * 
 * This script handles all barcode and QR code scanning functionality for Sherlock.
 * It manages a single, reusable scanner modal and attaches event listeners
 * to various buttons across the application to trigger different scanning workflows.
 * 
 * Dependencies: 
 *  - html5-qrcode.min.js (must be loaded before this script)
 *  - A modal element with the ID 'scanner-modal' in the base template.
 */

document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('scanner-modal');
    const closeButton = document.querySelector('.scanner-close-button');
    const qrReaderElement = document.getElementById('qr-reader');

    if (!modal || !closeButton || !qrReaderElement) {
        return;
    }

    let html5QrcodeScanner;

    const showScannerUnavailable = () => {
        qrReaderElement.innerHTML = '<p class="alert alert-warning">扫描组件未加载，请刷新页面或手动使用条码查询。</p>';
        modal.style.display = "block";
    };

    const renderScanner = (onSuccess) => {
        if (typeof Html5QrcodeScanner === 'undefined') {
            showScannerUnavailable();
            return;
        }
        if (!html5QrcodeScanner) {
            html5QrcodeScanner = new Html5QrcodeScanner("qr-reader", { fps: 10, qrbox: { width: 250, height: 250 } });
        }
        html5QrcodeScanner.render(onSuccess, (error) => {});
    };

    // --- Global Scanner Initialization and Controls ---

    const stopScannerAndCloseModal = () => {
        if (html5QrcodeScanner && typeof html5QrcodeScanner.clear === 'function') {
            html5QrcodeScanner.clear().catch(error => {
                console.error("Error while clearing the scanner:", error);
            });
        }
        modal.style.display = "none";
    };

    window.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && modal.style.display === 'block') {
            stopScannerAndCloseModal();
        }
    });

    closeButton.addEventListener('click', stopScannerAndCloseModal);
    window.addEventListener('click', (event) => {
        if (event.target == modal) {
            stopScannerAndCloseModal();
        }
    });

    // --- Workflow 1: Checkout Terminal Scanner ---

    const checkoutScanButton = document.getElementById('scan-item-button');
    const scannerForm = document.getElementById('scanner-form');
    const scannerBarcodeHiddenInput = document.getElementById('scanner-barcode-input');
    
    if (checkoutScanButton && scannerForm && scannerBarcodeHiddenInput) {
        
        const onCheckoutScanSuccess = (decodedText, decodedResult) => {
            console.log(`Checkout scan successful: ${decodedText}`);
            stopScannerAndCloseModal();
            scannerBarcodeHiddenInput.value = decodedText;
            scannerForm.requestSubmit();
        };

        checkoutScanButton.addEventListener('click', () => {
            modal.style.display = "block";
            renderScanner(onCheckoutScanSuccess);
        });
    }

    // --- Workflow 2: Universal Lookup Scanner ---

    const universalScanButton = document.getElementById('universal-scan-button');
    const searchPageScanButton = document.getElementById('search-page-scan-button');
    
    const onUniversalScanSuccess = (decodedText, decodedResult) => {
        console.log(`Universal scan successful: ${decodedText}`);
        stopScannerAndCloseModal();
        
        const lookupUrl = `/lookup/?code=${encodeURIComponent(decodedText)}`;
        window.location.href = lookupUrl;
    };

    const startUniversalScanner = () => {
        modal.style.display = "block";
        renderScanner(onUniversalScanSuccess);
    };

    if (universalScanButton) {
        universalScanButton.addEventListener('click', startUniversalScanner);
    }
    if (searchPageScanButton) {
        searchPageScanButton.addEventListener('click', startUniversalScanner);
    }
});
