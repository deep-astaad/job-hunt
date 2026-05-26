pipeline {
  agent any

  options {
    disableConcurrentBuilds()
    timestamps()
  }

  environment {
    IMAGE_NAME = 'ghcr.io/deep-astaad/job-hunt'
  }

  stages {
    stage('Build image') {
      steps {
        sh '''
          set -eu
          docker build \
            --tag "$IMAGE_NAME:$GIT_COMMIT" \
            --tag "$IMAGE_NAME:main" \
            .
        '''
      }
    }

    stage('Smoke check') {
      steps {
        sh '''
          set -eu
          docker run --rm \
            -e APIFY_API_TOKEN=dummy \
            -e OPENAI_API_KEY=dummy \
            --entrypoint python \
            "$IMAGE_NAME:$GIT_COMMIT" \
            backend/manage.py check
        '''
      }
    }

    stage('Publish image') {
      when {
        expression {
          env.BRANCH_NAME == 'main' || env.GIT_BRANCH == 'main' || env.GIT_BRANCH == 'origin/main'
        }
      }
      steps {
        withCredentials([usernamePassword(
          credentialsId: 'ghcr_access_hu',
          usernameVariable: 'GHCR_USER',
          passwordVariable: 'GHCR_TOKEN'
        )]) {
          sh '''
            set -eu
            echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin
            docker push "$IMAGE_NAME:$GIT_COMMIT"
            docker push "$IMAGE_NAME:main"
            docker logout ghcr.io
          '''
        }
      }
    }
  }
}
