IMAGE ?= gianlucavinci98/gpu-matmul-benchmark
TAG ?= 0.1.0
PLATFORM ?= linux/amd64

.PHONY: build push inspect

build:
	docker buildx build \
		--platform $(PLATFORM) \
		--build-arg IMAGE_VERSION=$(TAG) \
		--tag $(IMAGE):$(TAG) \
		--load .

push:
	docker buildx build \
		--platform $(PLATFORM) \
		--build-arg IMAGE_VERSION=$(TAG) \
		--tag $(IMAGE):$(TAG) \
		--push .

inspect:
	docker buildx imagetools inspect $(IMAGE):$(TAG)

