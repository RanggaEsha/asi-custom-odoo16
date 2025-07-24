// Send a beacon to close the session when the tab or browser is closed or hidden
function sendSessionEndBeacon() {
    console.log('[Audit] Sending session end beacon...');
    if (navigator.sendBeacon) {
        navigator.sendBeacon('/audit/session/end');
    } else {
        // Fallback for older browsers
        var xhr = new XMLHttpRequest();
        xhr.open('POST', '/audit/session/end', false);
        xhr.send();
    }
}

window.addEventListener('unload', sendSessionEndBeacon);

document.addEventListener('visibilitychange', function() {
    if (document.visibilityState === 'hidden') {
        sendSessionEndBeacon();
    }
});
