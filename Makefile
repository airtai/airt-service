SRC = $(wildcard notebooks/*.ipynb)

all: clean dist install alembic_migrate webservice.py site

airt_service: $(SRC) .build_installs
	nbdev_export
	black airt_service
	touch airt_service

dast: .dast_zast

.dast_zast:
	./scripts/dast.sh
	touch .dast_zast
    
sast: .sast_bandit .sast_semgrep

.sast_bandit: airt_service
	bandit -r airt_service
	touch .sast_bandit
    
.sast_semgrep: airt_service
	semgrep --config auto --error airt_service
	touch .sast_semgrep

docs/SUMMARY.md: dist
	airt-docs airt_service

docs/index.md: notebooks/index.ipynb dist
	jupyter nbconvert --to markdown --stdout --RegexRemovePreprocessor.patterns="['\# hide', '\#hide']" notebooks/index.ipynb | sed "s/{{ get_airt_service_version }}/$$(pip show airt-service | grep Version | cut -d ":" -f 2 | xargs)/" > docs/index.md

site: .build_installs install docs/index.md docs/SUMMARY.md
	mkdocs build
	cp docs/index.md README.md
	touch site
    
docs_serve: site
	mkdocs serve -a 0.0.0.0:6006

alembic_commit: install
	alembic revision --autogenerate -m '$(message)'

alembic_migrate: install
	check_db_is_up
	alembic upgrade head
	create_initial_users

empty_bucket:
	aws s3 ls | cut -d' ' -f3- | grep "^${STORAGE_BUCKET_PREFIX}" | xargs -I {} aws s3 rb --force s3://{}
	az login --service-principal --username ${AZURE_CLIENT_ID} --tenant ${AZURE_TENANT_ID} --password ${AZURE_CLIENT_SECRET}
	az storage account list --query "[*].name" -o tsv | grep "^${AZURE_STORAGE_ACCOUNT_PREFIX}" | xargs -I {} az storage account delete --yes --name {} --resource-group ${AZURE_RESOURCE_GROUP}

test: install mypy alembic_migrate empty_bucket
	nbdev_test --timing --do_print --path notebooks/DB_Models.ipynb
	nbdev_test --timing --do_print --pause 1 --skip_file_glob "DB_Models.ipynb"

release: pypi
	nbdev_bump_version

pypi: dist
	twine upload --repository pypi dist/*

dist: airt_service
	python setup.py sdist bdist_wheel
	touch dist
    
clean:
	rm -rf airt_service
	rm -rf airt_service.egg-info
	rm -rf build
	rm -rf dist
	rm -rf site
	rm -rf docs/index.md docs/SUMMARY.md docs/API
	rm -rf .build_installs
	pip uninstall -r build_and_test_requirements.txt -y
	pip uninstall airt-service -y

install_airt:
	./scripts/install_airt.sh

install_airflow:
	./scripts/install_airflow.sh

start_airflow: install_airflow
	./scripts/start_airflow.sh

install: dist install_airt start_airflow
	pip install --force-reinstall dist/airt_service-*-py3-none-any.whl

mypy: airt_service
	mypy airt_service --ignore-missing-imports

webservice.py: install
	jupyter nbconvert --to python notebooks/services/webservice.ipynb --output ../../webservice

serve_webservice: webservice.py alembic_migrate
	export JOB_EXECUTOR="fastapi"; uvicorn webservice:app --port 6006 --host 0.0.0.0 --reload; export JOB_EXECUTOR=""

batch_environment.yml:
	touch batch_environment.yml

build_and_check_docker_image: batch_environment.yml
	./ws/build_docker.sh

trivy_scan_repo:
	./scripts/trivy_scan_repo.sh

.build_installs: build_and_test_requirements.txt
	pip install -r build_and_test_requirements.txt
	touch .build_installs
