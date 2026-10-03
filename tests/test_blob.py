"""Tests de la synchronisation Blob sans Azure : le conteneur est simulé en mémoire."""

from cloud.blob import conteneur, envoyer, telecharger


class FakeBlob:
    def __init__(self, stockage, nom):
        self.stockage, self.nom = stockage, nom

    def exists(self):
        return self.nom in self.stockage

    def download_blob(self):
        return _Telechargement(self.stockage[self.nom])


class _Telechargement:
    def __init__(self, contenu):
        self.contenu = contenu

    def readinto(self, f):
        f.write(self.contenu)


class FakeConteneur:
    """Imite ContainerClient : un dict nom -> octets."""

    def __init__(self):
        self.stockage = {}

    def get_blob_client(self, nom):
        return FakeBlob(self.stockage, nom)

    def upload_blob(self, nom, f, overwrite=False):
        self.stockage[nom] = f.read()


def test_hors_cloud_ne_fait_rien(monkeypatch, tmp_path):
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    assert conteneur() is None
    assert telecharger(["telco360.duckdb"], tmp_path) == []
    assert envoyer(["telco360.duckdb"], tmp_path) == []


def test_aller_retour(tmp_path):
    blob = FakeConteneur()
    (tmp_path / "base.duckdb").write_bytes(b"donnees")
    assert envoyer(["base.duckdb"], tmp_path, blob) == ["base.duckdb"]

    arrivee = tmp_path / "arrivee"
    assert telecharger(["base.duckdb"], arrivee, blob) == ["base.duckdb"]
    assert (arrivee / "base.duckdb").read_bytes() == b"donnees"


def test_blob_absent_ignore(tmp_path):
    # 1er déploiement : la base n'existe pas encore dans Blob, le pipeline la créera
    assert telecharger(["base.duckdb"], tmp_path, FakeConteneur()) == []
