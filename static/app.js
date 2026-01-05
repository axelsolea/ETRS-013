// Affichage de la barre de chargement

document.querySelector('form').onsubmit = function(event) {
    // 1. EMPÊCHER LA SOUMISSION CLASSIQUE (pour ne pas recharger la page tout de suite)
    event.preventDefault();
    console.log("Form submitted via AJAX");

    const form = event.target;
    const formData = new FormData(form);
    const mainContainer = document.getElementById("main-container");

    // 2. AFFICHER L'INTERFACE DE CHARGEMENT
    mainContainer.innerHTML = `
        <div class="text-center" style="padding: 50px;">
            <div class="spinner-border text-primary" role="status" style="width: 3rem; height: 3rem;">
                <span class="visually-hidden">Chargement...</span>
            </div>
            <h3 id="status-text" class="mt-4">Connexion au serveur...</h3>
            <div class="progress mt-4" style="height: 25px; max-width: 500px; margin: 0 auto;">
                <div id="progress-bar" class="progress-bar progress-bar-striped progress-bar-animated" 
                     role="progressbar" style="width: 0%;" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
                     0%
                </div>
            </div>
            <p class="text-muted mt-2">Calcul de l'itinéraire et optimisation des bornes en cours...</p>
        </div>
    `;

    // 3. LANCER LE CALCUL (POST) EN ARRIÈRE-PLAN
    fetch('/computeTravel', {
        method: 'POST',
        body: formData
    })
    .then(response => response.text()) // On attend le HTML de retour (results.html)
    .then(html => {
        // Une fois le calcul fini (100%), on remplace toute la page par le résultat
        document.open();
        document.write(html);
        document.close();
    })
    .catch(error => {
        console.error('Erreur:', error);
        mainContainer.innerHTML = `<div class="alert alert-danger">Une erreur est survenue : ${error}</div>`;
    });

    // 4. LANCER LA SURVEILLANCE (POLLING) EN PARALLÈLE
    let errorCount = 0;
    const checkStatus = setInterval(() => {
        fetch('/flux_chargement')
            .then(res => res.json())
            .then(data => {
                const bar = document.getElementById("progress-bar");
                const text = document.getElementById("status-text");

                if (bar && text) {
                    // On ignore le message "Prêt" s'il apparaît au tout début
                    if (data.message !== "Prêt") {
                        bar.style.width = data.pourcentage + "%";
                        bar.innerText = data.pourcentage + "%";
                        text.innerText = data.message;
                    }

                    // Sécurité : Si on arrive à 100%, on arrête le polling (le .then du POST va prendre le relais)
                    if (data.pourcentage >= 100) {
                        clearInterval(checkStatus);
                        text.innerText = "Finalisation de l'affichage...";
                    }
                }
            })
            .catch(err => {
                console.error("Erreur de suivi:", err);
                errorCount++;
                if(errorCount > 10) clearInterval(checkStatus); // Arrêt d'urgence
            });
    }, 500); // Vérification toutes les 0.5 secondes
};