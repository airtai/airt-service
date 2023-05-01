SRC = $(wildcard notebooks/*.ipynb)

.PHONY: all
all: clean dist install .install_pre_commit_hooks alembic_migrate webservice.py # site

airt_service: $(SRC)
	nbdev_export
	touch airt_service

dast: dast_zast

dast_zast:
	echo "Dast not implemented yet"
	# ./scripts/dast.sh
    
sast: sast_bandit sast_semgrep

sast_bandit: airt_service
	bandit -r airt_service
	touch .sast_bandit
    
sast_semgrep: airt_service
	semgrep --config auto --error airt_service
	touch .sast_semgrep

# docs/SUMMARY.md: dist
# 	airt-docs airt_service

# docs/index.md: notebooks/index.ipynb dist
# 	jupyter nbconvert --to markdown --stdout --RegexRemovePreprocessor.patterns="['\# hide', '\#hide']" notebooks/index.ipynb | sed "s/{{ get_airt_service_version }}/$$(pip show airt-service | grep Version | cut -d ":" -f 2 | xargs)/" > docs/index.md

#docs/index.md docs/SUMMARY.md
# cp docs/index.md README.md
site: install
	nbdev_mkdocs docs
	touch site
    
docs_serve: site
	nbdev_mkdocs preview

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

check_secrets: .install_git_secrets_hooks .add_allowed_git_secrets
	git secrets --scan -r

check: mypy check_secrets detect_secrets sast dast trivy_scan_repo

test: install mypy alembic_migrate empty_bucket
	nbdev_test --timing --do_print --path notebooks/DB_Models.ipynb
	nbdev_test --timing --do_print --path notebooks/API_Web_Service.ipynb
	nbdev_test --timing --do_print --path notebooks/AWS_Batch_Job_Context.ipynb
	nbdev_test --timing --do_print --path notebooks/AWS_Batch_Job_Utils.ipynb
	nbdev_test --timing --do_print --path notebooks/AWS_Utils.ipynb
	nbdev_test --timing --do_print --path notebooks/AirflowAWSBatchExecutor.ipynb
	nbdev_test --timing --do_print --path notebooks/AirflowAzureBatchExecutor.ipynb
	nbdev_test --timing --do_print --path notebooks/AirflowBashExecutor.ipynb
	nbdev_test --timing --do_print --path notebooks/AirflowExecutor.ipynb
	nbdev_test --timing --do_print --path notebooks/Airflow_Utils.ipynb
	nbdev_test --timing --do_print --path notebooks/Auth.ipynb
	nbdev_test --timing --do_print --path notebooks/Azure_Batch_Job_Context.ipynb
	nbdev_test --timing --do_print --path notebooks/Azure_Batch_Job_Utils.ipynb
	nbdev_test --timing --do_print --path notebooks/Azure_Utils.ipynb
	nbdev_test --timing --do_print --path notebooks/Background_Task.ipynb
	nbdev_test --timing --do_print --path notebooks/BaseAirflowExecutor.ipynb
	nbdev_test --timing --do_print --path notebooks/Base_Batch_Job_Context.ipynb
	nbdev_test --timing --do_print --path notebooks/BatchJob.ipynb
	nbdev_test --timing --do_print --path notebooks/Cleanup.ipynb
	nbdev_test --timing --do_print --path notebooks/Confluent.ipynb
	nbdev_test --timing --do_print --path notebooks/Constants.ipynb
	nbdev_test --timing --do_print --path notebooks/DataBlob_Azure_Blob_Storage.ipynb
	nbdev_test --timing --do_print --path notebooks/DataBlob_Clickhouse.ipynb
	nbdev_test --timing --do_print --path notebooks/DataBlob_DB.ipynb
	nbdev_test --timing --do_print --path notebooks/DataBlob_Router.ipynb
	nbdev_test --timing --do_print --path notebooks/DataBlob_S3.ipynb
	nbdev_test --timing --do_print --path notebooks/DataSource_CSV.ipynb
	nbdev_test --timing --do_print --path notebooks/DataSource_Parquet.ipynb
	nbdev_test --timing --do_print --path notebooks/DataSource_Router.ipynb
	nbdev_test --timing --do_print --path notebooks/Data_Utils.ipynb
	nbdev_test --timing --do_print --path notebooks/Errors.ipynb
	nbdev_test --timing --do_print --path notebooks/FastAPI_Batch_Job_Context.ipynb
	nbdev_test --timing --do_print --path notebooks/Helpers.ipynb
	nbdev_test --timing --do_print --path notebooks/Integration_Test.ipynb
	nbdev_test --timing --do_print --path notebooks/Kafka_Service.ipynb
	nbdev_test --timing --do_print --path notebooks/Model_Prediction.ipynb
	nbdev_test --timing --do_print --path notebooks/Model_Train.ipynb
	nbdev_test --timing --do_print --path notebooks/None_Batch_Job_Context.ipynb
	nbdev_test --timing --do_print --path notebooks/SMS_Utils.ipynb
	nbdev_test --timing --do_print --path notebooks/SSO.ipynb
	nbdev_test --timing --do_print --path notebooks/Sanitize_Secrets.ipynb
	nbdev_test --timing --do_print --path notebooks/TOTP.ipynb
	nbdev_test --timing --do_print --path notebooks/Users.ipynb
	nbdev_test --timing --do_print --path notebooks/Uvicorn_Helpers.ipynb
	nbdev_test --timing --do_print --path notebooks/index.ipynb    
nothing:    
	nbdev_test --timing --do_print --path notebooks/API_Web_Service.ipynb
	nbdev_test --timing --do_print --path notebooks/Kafka_Service.ipynb
	nbdev_test --n_workers 1 --timing --do_print --pause 1 --skip_file_re "^([_.]|DB_Models|API_Web_Service|Kafka_Service)" 

release: pypi
	nbdev_bump_version

pypi: dist
	twine upload --repository pypi dist/*

dist: airt_service
	python3 setup.py sdist bdist_wheel
	touch dist

.PHONY: prepare
prepare: all check test
	nbdev_clean

clean:
	rm -rf airt_service
	rm -rf airt_service.egg-info
	rm -rf build
	rm -rf dist
	rm -rf site
	rm -rf mkdocs/docs/
	rm -rf mkdocs/site/
	pip uninstall airt-service -y

install_airt:
	./scripts/install_airt.sh

install_airflow:
	./scripts/install_airflow.sh

start_airflow: install_airflow
	./scripts/start_airflow.sh

.install_git_secrets_hooks:
	git secrets --install -f
	git secrets --register-aws
	touch .install_git_secrets_hooks

.add_allowed_git_secrets: .install_git_secrets_hooks allowed_secrets.txt
	git secrets --add -a "dummy"
	git config --unset-all secrets.allowed
	cat allowed_secrets.txt | xargs -I {} git secrets --add -a {}
	touch .add_allowed_git_secrets

.install_pre_commit_hooks:
	pre-commit install
	touch .install_pre_commit_hooks

export PATH := $(HOME)/.local/bin:$(PATH)

install: dist install_airt start_airflow
	pip install -e '.[dev]'
#export PATH=$PATH:/home/kumaran/.local/bin
#pip install --force-reinstall dist/airt_service-*-py3-none-any.whl

mypy: install
	mypy airt_service

check_git_history_for_secrets: .add_allowed_git_secrets
	git secrets --scan-history

detect_secrets: airt_service
	git ls-files -z | xargs -0 detect-secrets-hook --baseline .secrets.baseline

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
